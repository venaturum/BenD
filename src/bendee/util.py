from dataclasses import dataclass
from typing import List

import numpy as np


@dataclass
class MasterResult:
    objval: float
    thetas: List[float]
    solution: np.ndarray


@dataclass
class CutRHS:
    intercept: float
    coeffs: np.ndarray


@dataclass
class SubproblemResult:
    infeasible: bool
    objval_sub: float
    cutRHS: CutRHS
    subproblem_num: int
    solution: np.ndarray
    solution_offset: np.ndarray | None = None

    @property
    def X(self):
        return (
            self.solution
            if self.solution_offset is None
            else self.solution + self.solution_offset
        )
