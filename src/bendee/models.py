import logging
from typing import Any, Callable, List, Tuple, Type

import gurobipy as gp
import numpy as np

from bendee._typing import MasterProblem as MasterproblemProtocol
from bendee._typing import Subproblem
from bendee.config import SubproblemLpForm as SubForm
from bendee.config import SubproblemReturn as SubReturn
from bendee.config import _defaults as config_defaults
from bendee.solution import SolutionStats
from bendee.staging import MasterData, SubproblemData
from bendee.util import CutRHS, MasterResult, SubproblemResult


def get_subproblem_class(lp_form: SubForm, sub_return: SubReturn) -> Type[Subproblem]:
    return {
        (SubForm.primal, SubReturn.duals): PrimalParamX,
        (SubForm.primal, SubReturn.subgradient): PrimalVariableX,
        (SubForm.dual, SubReturn.duals): DualParamX,
        (SubForm.dual, SubReturn.subgradient): DualVariableX,
    }[(lp_form, sub_return)]


class MasterProblem(MasterproblemProtocol):
    def __init__(
        self,
        data: MasterData,
        theta_lb: int = config_defaults.theta_lb,
        params: dict[str, Any] | None = None,
    ) -> None:
        self.model: gp.Model = data.model.copy()
        self._dummy_binary_added = False
        self._is_continuous_model = data.is_continuous_model

        default_params = {"OutputFlag": 0}
        params = {**default_params, **params} if params else default_params
        for param, val in params.items():
            self.model.setParam(param, val)

        self.vars: gp.MVar = gp.MVar.fromlist(self.model.getVars())
        self.thetas: List[gp.Var] = [
            self.model.addVar(lb=theta_lb, obj=1, name=f"theta_{i}")
            for i in range(data.num_subproblems)
        ]

    def set_params_for_callback(self) -> None:
        self.model.params.LazyConstraints = 1
        self.model.params.OutputFlag = 1

    def ensure_mip(self) -> None:
        if self._is_continuous_model:
            self._dummy_binary_added = True
            self.model.addVar(vtype="B", name="dummy_mip")

    def optimize(self, callback: Callable | None = None) -> MasterResult:
        self.model.optimize(callback)
        solution = self.vars.getAttr("X")
        if self._dummy_binary_added:
            solution = solution[:-1]
        master_result = MasterResult(
            objval=self.model.ObjVal,
            thetas=[theta.X for theta in self.thetas],
            solution=self.vars.getAttr("X"),
        )
        logging.debug(f"master: objective {master_result.objval}")
        logging.debug(f"master: thetas {[theta.X for theta in self.thetas]}")
        logging.debug(f"master: solution {master_result.solution}")
        return master_result

    def get_solution_stats(self):
        return SolutionStats(
            self.model.Runtime,
            self.model.ObjVal,
            self.model.ObjBound,
            self.model.MIPGap,
        )

    def get_callback_result(self) -> MasterResult:
        master_result = MasterResult(
            self.model.cbGet(gp.GRB.Callback.MIPSOL_OBJ),
            self.model.cbGetSolution(self.thetas),
            self.model.cbGetSolution(self.vars),
        )
        # logging.debug(f"master objective {master_result.objval}")
        # # logging.debug(f"master theta {master_result.theta}")
        # logging.debug(f"master solution {master_result.solution}")
        return master_result

    def add_constraint(
        self, lazy: bool, infeasible: bool, cutRHS: CutRHS, subproblem_num: int
    ) -> None:
        if infeasible:
            logging.debug("adding feasibility cut")
        else:
            logging.debug("adding optimality cut")
        LHS = 0 if infeasible else self.thetas[subproblem_num]
        expr = LHS >= cutRHS.intercept + cutRHS.coeffs @ self.vars
        if lazy:
            self.model.cbLazy(expr)
        else:
            self.model.addConstr(expr)


class PrimalParamX(Subproblem):
    def __init__(
        self,
        data: SubproblemData,
        reset_subproblem: bool = config_defaults.reset_subproblem,
        env: gp.Env | None = None,
        params: dict[str, Any] | None = None,
    ) -> None:
        self.reset_subproblem: bool = reset_subproblem
        data.transform(translate_lb=True, ub_constraints=True)
        self.data: SubproblemData = data
        self.env = env
        self.y, self.constrs, self.model = self._make_subproblem(data)
        self._set_params(params)

    def close(self):
        self.model.close()

    def _set_params(self, params: dict[str, Any] | None):
        default_params = {"OutputFlag": 0, "InfUnbdInfo": 1}
        major = gp.gurobi.version()[0]
        if major >= 11:
            default_params["ConcurrentMethod"] = 3
        else:
            default_params["Method"] = 5

        params = {**default_params, **params} if params else default_params
        for param, val in params.items():
            self.model.setParam(param, val)

    def _make_subproblem(
        self,
        data: SubproblemData,
    ) -> Tuple[gp.MVar, gp.MConstr, gp.Model]:
        if self.env is None:
            subproblem = gp.Model()
        else:
            subproblem = gp.Model(env=self.env)
        y = subproblem.addMVar(data.num_continuous_vars)
        constrs = subproblem.addConstr(data.B @ y >= 0)
        subproblem.setObjective(data.c @ y + data.c_const)
        subproblem.update()  # needed?
        return y, constrs, subproblem

    def solve(self, master_result: MasterResult) -> SubproblemResult:
        if self.reset_subproblem:
            self.model.reset_subproblem()
        self.constrs.RHS = self.data.b - self.data.A @ master_result.solution
        self.model.optimize()
        infeasible = self.model.Status in (
            gp.GRB.Status.INF_OR_UNBD,
            gp.GRB.Status.INFEASIBLE,
        )
        if infeasible:
            duals = -np.array(self.model.farkasdual)
        else:
            duals = np.array(self.constrs.Pi).flatten()
        cutRHS = CutRHS(
            intercept=self.data.b @ duals,
            coeffs=-(duals @ self.data.A),
        )
        result = SubproblemResult(
            infeasible=infeasible,
            objval_sub=self.model.ObjVal,
            cutRHS=cutRHS,
            subproblem_num=self.data.subproblem_num,
            solution=self.y.getAttr("X"),
            solution_offset=self.data.lb if self.data.offset else None,
        )
        logging.debug(f"sub: infeasible = {result.infeasible}")
        logging.debug(f"sub: obj_sub = {result.objval_sub}")
        logging.debug(f"sub: cutRHS = {result.cutRHS}")
        return result


class PrimalVariableX(Subproblem):
    def __init__(
        self,
        data: SubproblemData,
        reset_subproblem: bool = config_defaults.reset_subproblem,
        env: gp.Env | None = None,
        params: dict[str, Any] | None = None,
    ) -> None:
        self.reset_subproblem = reset_subproblem
        self.env = env
        self.data = data  # no need to transform subproblem data, we can use bounds
        self.subproblem_num = data.subproblem_num
        self.zero_obj = data.zero_obj
        self.x, self.y, self.model = self._make_subproblem(data)
        self._set_params(params)

    def close(self):
        self.model.close()

    def _set_params(self, params: dict[str, Any] | None):
        # Primal simplex only algorithm that works
        default_params = {"OutputFlag": 0, "InfUnbdInfo": 1, "Method": 0}

        params = {**default_params, **params} if params else default_params
        for param, val in params.items():
            self.model.setParam(param, val)

    def _make_subproblem(
        self, data: SubproblemData
    ) -> Tuple[gp.MVar, gp.MVar, gp.Model]:
        if self.env is None:
            subproblem = gp.Model()
        else:
            subproblem = gp.Model(name="SUB", env=self.env)
        x = subproblem.addMVar(data.num_integer_vars)
        y = subproblem.addMVar(data.num_continuous_vars, lb=data.lb, ub=data.ub)
        if data.zero_obj:
            s = subproblem.addMVar(len(data.b))
            subproblem.addConstr(data.A @ x + data.B @ y + s.sum() >= data.b)
            subproblem.setObjective(s.sum() + data.c_const)  # TODO: needed?
        else:
            subproblem.addConstr(data.A @ x + data.B @ y >= data.b)
            subproblem.setObjective(data.c @ y + data.c_const)
        return x, y, subproblem

    def _is_infeasible(self):
        if self.zero_obj:
            infeasible = self.model.ObjVal > 0
        else:
            infeasible = self.model.Status in (
                gp.GRB.Status.INF_OR_UNBD,
                gp.GRB.Status.INFEASIBLE,
            )
        return infeasible

    def solve(self, master_result: MasterResult) -> SubproblemResult:
        if self.reset_subproblem:
            self.model.reset()
        self.x.setAttr("LB", master_result.solution)
        self.x.setAttr("UB", master_result.solution)
        self.model.optimize()
        infeasible = self._is_infeasible()
        subgradient = np.array(self.x.RC)
        logging.debug(f"sub: subgradient = {subgradient}")
        cutRHS = CutRHS(
            intercept=self.model.ObjVal - master_result.solution @ subgradient,
            coeffs=subgradient,
        )

        result = SubproblemResult(
            infeasible=infeasible,
            objval_sub=self.model.ObjVal,
            cutRHS=cutRHS,
            subproblem_num=self.subproblem_num,
            solution=self.y.getAttr("X"),
            solution_offset=self.data.lb if self.data.offset else None,
        )
        logging.debug(f"sub: obj_sub = {result.objval_sub}")
        logging.debug(f"sub: cutRHS = {result.cutRHS}")
        return result


class DualParamX(Subproblem):
    def __init__(
        self,
        data: SubproblemData,
        reset_subproblem: bool = config_defaults.reset_subproblem,
        env: gp.Env | None = None,
        params: dict[str, Any] | None = None,
    ) -> None:
        self.reset_subproblem = reset_subproblem
        self.env = env
        data.transform(translate_lb=True, ub_constraints=True)
        self.data = data
        self.y, self.dual_cons, self.model = self._make_subproblem(data)
        self._set_params(params)

    def close(self):
        self.model.close()

    def _set_params(self, params: dict[str, Any] | None):
        default_params = {"OutputFlag": 0, "InfUnbdInfo": 1}
        major = gp.gurobi.version()[0]
        if major >= 11:
            default_params["ConcurrentMethod"] = 3
        else:
            default_params["Method"] = 5

        params = {**default_params, **params} if params else default_params
        for param, val in params.items():
            self.model.setParam(param, val)

    def _make_subproblem(
        self, data: SubproblemData
    ) -> Tuple[gp.MVar, gp.MConstr, gp.Model]:
        if self.env is None:
            subproblem = gp.Model()
        else:
            subproblem = gp.Model(env=self.env)
        y = subproblem.addMVar(len(data.b))
        dual_cons = subproblem.addConstr(y @ data.B <= data.c)
        subproblem.setObjective(data.c_const, gp.GRB.MAXIMIZE)
        subproblem.update()  # needed?
        return y, dual_cons, subproblem

    def solve(self, master_result: MasterResult) -> SubproblemResult:
        if self.reset_subproblem:
            self.model.reset()
        self.y.Obj = self.data.b - self.data.A @ master_result.solution
        self.model.optimize()
        unbounded = self.model.Status in (
            gp.GRB.Status.INF_OR_UNBD,
            gp.GRB.Status.UNBOUNDED,
        )
        if unbounded:
            duals = np.array(self.model.UnbdRay)
        else:
            duals = np.array(self.y.X).flatten()
        cutRHS = CutRHS(
            intercept=self.data.b @ duals,
            coeffs=-duals @ self.data.A,
        )
        result = SubproblemResult(
            infeasible=unbounded,
            objval_sub=self.model.ObjVal,
            cutRHS=cutRHS,
            subproblem_num=self.data.subproblem_num,
            solution=self.dual_cons.getAttr("Pi"),
            solution_offset=self.data.lb if self.data.offset else None,
        )
        logging.debug(f"sub: infeasible = {result.infeasible}")
        logging.debug(f"sub: obj_sub = {result.objval_sub}")
        logging.debug(f"sub: cutRHS = {result.cutRHS}")
        return result


class DualVariableX(Subproblem):
    """_summary_

    Parameters
    ----------
    Subproblem : _type_
        _description_
    """

    # min du + vx'
    # uA + v <= 0
    # uB <= c
    # u >= 0
    def __init__(
        self,
        data: SubproblemData,
        reset_subproblem: bool = config_defaults.reset_subproblem,
        env: gp.Env | None = None,
        params: dict[str, Any] | None = None,
    ) -> None:
        self.reset_subproblem = reset_subproblem
        self.env = env
        data.transform(translate_lb=True, ub_constraints=True)
        self.data = data
        self.subproblem_num = data.subproblem_num
        self.zero_obj = data.zero_obj
        self.u, self.dual_cons, self.model = self._make_subproblem(data)
        self._set_params(params)

    def close(self):
        self.model.close()

    def _set_params(self, params: dict[str, Any] | None):
        default_params = {"OutputFlag": 0, "InfUnbdInfo": 1}
        major = gp.gurobi.version()[0]
        if major >= 11:
            default_params["ConcurrentMethod"] = 3
        else:
            default_params["Method"] = 5

        params = {**default_params, **params} if params else default_params
        for param, val in params.items():
            self.model.setParam(param, val)

    def _make_subproblem(
        self, data: SubproblemData
    ) -> Tuple[gp.MVar, gp.MConstr, gp.Model]:
        if self.env is None:
            subproblem = gp.Model()
        else:
            subproblem = gp.Model(env=self.env)
        ub = 1 if data.zero_obj else float("inf")
        y = subproblem.addMVar(data.A.shape[0], ub=ub)
        u = subproblem.addMVar(data.num_integer_vars, lb=-float("inf"))
        dual_cons = subproblem.addConstr(y @ data.B <= data.c)
        subproblem.addConstr(y @ data.A + u <= 0)
        subproblem.setObjective(data.b @ y + data.c_const, gp.GRB.MAXIMIZE)
        subproblem.update()  # needed?
        return u, dual_cons, subproblem

    def solve(self, master_result: MasterResult) -> SubproblemResult:
        if self.reset_subproblem:
            self.model.reset()
        self.u.setAttr("Obj", master_result.solution)
        self.model.optimize()
        if self.zero_obj:
            unbounded = self.model.ObjVal > 0
        else:
            unbounded = self.model.Status in (
                gp.GRB.Status.INF_OR_UNBD,
                gp.GRB.Status.UNBOUNDED,
            )
        if not self.zero_obj and unbounded:
            subgradient = np.array(self.model.UnbdRay)[-self.data.num_integer_vars :]
            cutRHS = CutRHS(
                intercept=self.data.b
                @ np.array(self.model.UnbdRay)[: len(self.data.b)],
                coeffs=subgradient,
            )
        else:
            subgradient = np.array(self.u.X)
            cutRHS = CutRHS(
                intercept=self.model.ObjVal - master_result.solution @ subgradient,
                coeffs=subgradient,
            )
        result = SubproblemResult(
            infeasible=unbounded,
            objval_sub=self.model.ObjVal,
            cutRHS=cutRHS,
            subproblem_num=self.subproblem_num,
            solution=self.dual_cons.getAttr("Pi"),
            solution_offset=self.data.lb if self.data.offset else None,
        )
        logging.debug(f"sub: obj_sub = {result.objval_sub}")
        logging.debug(f"sub: cutRHS = {result.cutRHS}")
        return result
