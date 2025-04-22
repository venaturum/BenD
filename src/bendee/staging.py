import logging
from dataclasses import dataclass
from typing import List

import gurobipy as gp
import numpy as np
import scipy.sparse as ss


@dataclass
class MasterData:
    model: gp.Model
    num_subproblems: int
    is_continuous_model: bool


@dataclass
class SubproblemData:
    A: ss.csr_matrix
    B: ss.csr_matrix
    b: np.ndarray
    c: np.ndarray
    c_const: float
    lb: np.ndarray  # will never change even if lbs are adjusted
    ub: np.ndarray  # will change if variables translated
    subproblem_num: int
    offset: bool = False

    @property
    def num_continuous_vars(self):
        return self.B.shape[1]

    @property
    def num_integer_vars(self):
        return self.A.shape[1]

    @property
    def zero_obj(self):
        return all(self.c == 0)

    def transform(self, translate_lb: bool, ub_constraints: bool) -> None:
        if translate_lb:
            self.offset = True
            self.b -= self.B @ self.lb
            self.c_const += self.c @ self.lb
            self.ub -= self.lb

        if ub_constraints:
            idx_finite_ubs = np.nonzero(self.ub != float("inf"))[0]
            B_ub = ss.csr_array(
                (
                    [-1] * len(idx_finite_ubs),  # data
                    (range(len(idx_finite_ubs)), idx_finite_ubs),  # (row ind, col ind)
                ),
                shape=(len(idx_finite_ubs), self.B.shape[1]),
            )
            self.B = ss.vstack([self.B, B_ub])
            self.b = np.concatenate([self.b, -self.ub[idx_finite_ubs]])
            self.A = ss.vstack(
                [self.A, ss.csr_array((len(idx_finite_ubs), self.A.shape[1]))]
            )


@dataclass
class ProblemData:
    master: MasterData
    subproblems: List[SubproblemData]

    def __del__(self):
        self.master.model.dispose()


class ProblemSpec:
    def __init__(self, model: gp.Model) -> None:
        self._finalized = False
        self._model: gp.Model = model
        self._complicating_vars: List[int] = []
        self.non_complicating_vars: List[List[int]] = []
        self.is_continuous_model = all(v.VType == "C" for v in model.getVars())

    def _assert_not_finalized(self):
        if self._finalized:
            raise RuntimeError

    def set_complicating_vars(self, vars: List[gp.Var]) -> None:
        self._assert_not_finalized()
        self.complicating_vars = [v.index for v in vars]

    def add_non_complicating_vars(self, vars: List[gp.Var]) -> None:
        self._assert_not_finalized()
        self.non_complicating_vars.append([v.index for v in vars])

    def make_problem_data(self) -> ProblemData:
        self._finalized = True

        self._add_missing_indices()
        logging.debug("adding_missing_indices")
        self._check_non_complicating_vars()
        logging.debug("_check_non_complicating_vars")
        self._make_constraint_sets()
        logging.debug("_make_constraint_sets")
        self._check_independent_subproblems()
        logging.debug("_check_independent_subproblems")
        num_subproblems = len(self.non_complicating_vars)
        return ProblemData(
            MasterData(
                self._make_master_model(), num_subproblems, self.is_continuous_model
            ),
            [self._make_subproblem_data(i) for i in range(num_subproblems)],
        )

    def _add_missing_indices(self):
        inds = set(range(self._model.NumVars))
        inds -= set(self.complicating_vars)
        for vars_list in self.non_complicating_vars:
            inds -= set(vars_list)
        if len(inds):
            self.non_complicating_vars.append(list(inds))

    def _check_non_complicating_vars(self):
        vtype = self._model.VType
        subproblem_contains_non_continouous = any(
            [vtype[i] != "C" for i in self._subproblem_variable_indices]
        )
        if subproblem_contains_non_continouous:
            raise ValueError

    def _make_constraint_sets(self):
        A = self._model.getA().tocsc()  # .indices will give us rows
        self.master_constraint_inds = list(set(A[:, self.complicating_vars].indices))
        self.subproblem_constraint_inds = [
            set(A[:, vars_list].indices) for vars_list in self.non_complicating_vars
        ]

    def _check_independent_subproblems(self):
        if len(self.non_complicating_vars) <= 1:
            return True
        for j in range(1, len(self.subproblem_constraint_inds)):
            for i in range(j):
                if not self.subproblem_constraint_inds[i].isdisjoint(
                    self.subproblem_constraint_inds[j]
                ):
                    raise RuntimeError(
                        f"subproblems {i} and {j} have overlapping constraints"
                    )

    @property
    def _subproblem_variable_indices(self) -> List[int]:
        return [i for vars_list in self.non_complicating_vars for i in vars_list]

    @property
    def _subproblem_constraint_indices(self) -> List[int]:
        constraint_indices = set()
        for s in self.subproblem_constraint_inds:
            constraint_indices.update(s)
        return list(constraint_indices)

    def _make_master_model(self) -> gp.Model:
        # does not include theta
        logging.debug("making master model")
        master = self._model.copy()
        if master.ModelSense == gp.GRB.MAXIMIZE:
            master.setObjective(-master.getObjective(), gp.GRB.MINIMIZE)
        vars = master.getVars()
        constrs = master.getConstrs()
        master.remove([constrs[i] for i in self._subproblem_constraint_indices])
        master.remove([vars[i] for i in self._subproblem_variable_indices])
        # if self.is_continuous_model:
        #     master.addVar(vtype="B", name="dummy_var")
        master.update()
        logging.debug("made master model")
        return master

    def _make_subproblem_data(self, subproblem_num: int) -> SubproblemData:
        logging.debug("making subproblem data")
        var_indices: List = self.non_complicating_vars[subproblem_num]
        constr_indices: List = list(self.subproblem_constraint_inds[subproblem_num])
        c = np.array(self._model.obj)[var_indices]

        if self._model.ModelSense == gp.GRB.MAXIMIZE:
            c = -c

        b = np.array(self._model.RHS)[constr_indices]
        sense = np.array(self._model.Sense)[constr_indices]
        A = self._model.getA()[constr_indices][:, self.complicating_vars]
        B = self._model.getA()[constr_indices][:, var_indices]

        le_inds = np.reshape(np.where(sense == "<", -1, 1), (-1, 1))
        b = b * le_inds.flatten()
        A = A.multiply(le_inds).tocsr()
        B = B.multiply(le_inds).tocsr()
        eq_inds = (sense == "=").nonzero()[0]

        A = ss.vstack((A, -A[eq_inds, :]))
        B = ss.vstack((B, -B[eq_inds, :]))
        b = np.concatenate((b, -b[eq_inds]))
        logging.debug("made subproblem data")
        return SubproblemData(
            A=A,
            B=B,
            b=b,
            c=c,
            c_const=0,
            lb=np.array(self._model.lb)[var_indices],
            ub=np.array(self._model.ub)[var_indices],
            subproblem_num=subproblem_num,
        )
