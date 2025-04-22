from dataclasses import dataclass
from itertools import chain
from typing import List

import numpy as np

from bendee.staging import ProblemSpec
from bendee.util import MasterResult, SubproblemResult


@dataclass
class SolutionStats:
    Runtime: float | None = None
    ObjVal: float | None = None
    ObjBound: float | None = None
    MIPGap: float | None = None


class Result:
    def __init__(
        self,
        master_result: MasterResult,
        subproblem_results: List[SubproblemResult],
        solution_stats: SolutionStats,
    ):
        self._master_result: MasterResult = master_result
        self._subproblem_results: List[SubproblemResult] = subproblem_results
        self._solution_stats: SolutionStats = solution_stats
        self._X: np.ndarray | None = None
        self._vtype: List[str] | None = None
        self._varname: List[str] | None = None

    def resolve(self, problem_spec: ProblemSpec):
        var_inds = list(
            chain(
                problem_spec.complicating_vars,
                *problem_spec.non_complicating_vars,
            )
        )

        var_values = np.array(
            list(
                chain(
                    self._master_result.solution,
                    *[
                        subproblem_result.X
                        for subproblem_result in self._subproblem_results
                    ],
                )
            )
        )
        self._X = var_values[np.argsort(var_inds)]
        self._vtype = problem_spec._model.VType
        self._varname = problem_spec._model.VarName

    @property
    def X(self):
        return self._X

    @property
    def ObjVal(self):
        return self._solution_stats.ObjVal

    @property
    def ObjBound(self):
        return self._solution_stats.ObjBound

    @property
    def Runtime(self):
        return self._solution_stats.Runtime

    @property
    def MIPGap(self):
        return self._solution_stats.MIPGap

    def stats_string(self):
        return str(self._solution_stats)

    def write(self, filename: str) -> None:
        if self._X is None or self._varname is None or self._vtype is None:
            return
        ext = filename.split(".")[-1]
        if ext not in ("sol", "mst"):
            raise ValueError(
                f"File has extension .{ext} but must extension .sol or .mst"
            )
        include = " ".__ne__ if ext == "sol" else "C".__ne__
        with open(filename, "w") as file:
            for name, x, vtype in zip(self._varname, self._X, self._vtype):
                if include(vtype):
                    print(f"{name} {x}", file=file)
