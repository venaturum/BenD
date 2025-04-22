import time
from typing import List, Type

import gurobipy as gp

from bendee import config
from bendee._logging import consolelog
from bendee._typing import Framework, Subproblem
from bendee.config import _defaults as config_defaults
from bendee.models import MasterProblem
from bendee.solution import Result, SolutionStats


def get_framework_class(framework_value: config.Framework) -> Type[Framework]:
    return {
        config.Framework.callback: CallbackFramework,
        config.Framework.iterative: IterativeFramework,
    }[framework_value]


class IterativeFramework(Framework):
    def __init__(self, master: MasterProblem, subproblems: List[Subproblem]) -> None:
        self.master: MasterProblem = master
        self.subproblems: List[Subproblem] = subproblems

    def solve(
        self,
        optimality_gap: float = config_defaults.iterative_framework_optimality_gap,
        timelimit: float = config_defaults.iterative_framework_timelimit,
        max_iterations: int = config_defaults.max_iterations,
    ) -> Result:
        COLWIDTH = 20
        start_time = time.time()
        upper_bound = float("inf")

        consolelog.info(
            f"{'Iteration':>{COLWIDTH}} {'Lower Bound':>{COLWIDTH}} {'Upper Bound':>{COLWIDTH}} {'Gap':>{COLWIDTH}}"
        )
        for k in range(max_iterations):
            master_result = self.master.optimize()
            lower_bound = master_result.objval
            subproblem_results = [
                subproblem.solve(master_result) for subproblem in self.subproblems
            ]
            if all(not result.infeasible for result in subproblem_results):
                upper_bound = min(
                    master_result.objval
                    + sum(
                        result.objval_sub - theta
                        for result, theta in zip(
                            subproblem_results, master_result.thetas
                        )
                    ),
                    upper_bound,
                )
                if upper_bound == 0:
                    gap = float("inf")
                else:
                    gap = abs((upper_bound - lower_bound) / upper_bound)
                consolelog.info(
                    f"{f'iter {k}':>{COLWIDTH}} {lower_bound:>{COLWIDTH}.6f} {upper_bound:>{COLWIDTH}.6f} {f'{gap * 100:.2f}%':>{COLWIDTH}}"
                )
                current_runtime = time.time() - start_time
                if (gap < optimality_gap) or (current_runtime > timelimit):
                    solution_stats = SolutionStats(
                        Runtime=current_runtime,
                        ObjVal=upper_bound,
                        ObjBound=lower_bound,
                        MIPGap=gap,
                    )
                    if current_runtime > timelimit:
                        termination_message = "Reached timelimit"
                    else:
                        termination_message = "Achieved optimality gap"
                    consolelog.info(
                        f"Terminating.  {termination_message}. Objective value: {upper_bound}"
                    )
                    break
            else:
                consolelog.info(
                    f"{f'iter {k}':>{COLWIDTH}} {'----':>{COLWIDTH}} {'----':>{COLWIDTH}} {'----':>{COLWIDTH}}"
                )
            for result in subproblem_results:
                self.master.add_constraint(
                    lazy=False,
                    infeasible=result.infeasible,
                    cutRHS=result.cutRHS,
                    subproblem_num=result.subproblem_num,
                )
        return Result(
            master_result=master_result,
            subproblem_results=subproblem_results,
            solution_stats=solution_stats,
        )


class CallbackFramework(Framework):
    def __init__(self, master: MasterProblem, subproblems: List[Subproblem]) -> None:
        self.master: MasterProblem = master
        self.subproblems: List[Subproblem] = subproblems
        self.master.set_params_for_callback()
        self.best_obj = float("inf")

    def __call__(self, _, where):
        if where == gp.GRB.Callback.MIPSOL:
            master_result = self.master.get_callback_result()
            subproblem_results = [
                subproblem.solve(master_result) for subproblem in self.subproblems
            ]
            for result in subproblem_results:
                self.master.add_constraint(
                    lazy=True,
                    infeasible=result.infeasible,
                    cutRHS=result.cutRHS,
                    subproblem_num=result.subproblem_num,
                )

    def solve(self) -> Result:
        self.master.ensure_mip()
        master_result = self.master.optimize(self)
        subproblem_results = [
            subproblem.solve(master_result) for subproblem in self.subproblems
        ]
        return Result(
            master_result=master_result,
            subproblem_results=subproblem_results,
            solution_stats=self.master.get_solution_stats(),
        )
