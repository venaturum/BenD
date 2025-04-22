from typing import Any, List, Protocol

import gurobipy as gp

from bendee.solution import Result
from bendee.staging import SubproblemData
from bendee.util import MasterResult, SubproblemResult


class MasterProblem(Protocol): ...


class Subproblem(Protocol):
    def __init__(
        self,
        data: SubproblemData,
        reset_subproblem: bool,
        env: gp.Env,
        params: dict[str, Any] | None,
    ) -> None: ...
    def solve(self, master_result: MasterResult) -> SubproblemResult: ...
    def close(self) -> None: ...


class Framework(Protocol):
    def __init__(
        self, master: MasterProblem, subproblems: List[Subproblem]
    ) -> None: ...
    def solve(self, *args, **kwargs) -> Result: ...
