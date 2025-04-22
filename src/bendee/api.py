import gurobipy as gp

from bendee._logging import consolelog
from bendee.config import Config
from bendee.framework import get_framework_class
from bendee.models import MasterProblem, get_subproblem_class
from bendee.solution import Result
from bendee.staging import ProblemSpec


def solve(problem_spec: ProblemSpec, config: Config, env: gp.Env) -> Result:
    """The solve function

    Parameters
    ----------
    problem_spec : ProblemSpec
        _description_
    config : Config
        _description_
    """

    data = problem_spec.make_problem_data()

    framework_class = get_framework_class(config.framework)
    subproblem_class = get_subproblem_class(config.lp_form, config.sub_return)

    master = MasterProblem(
        data.master, theta_lb=config.theta_lb, params=config.master_params
    )
    subproblems = [
        subproblem_class(
            subproblem,
            config.reset_subproblem,
            env=env,
            params=config.subproblem_params,
        )
        for subproblem in data.subproblems
    ]

    algo = framework_class(master, subproblems)
    result: Result = algo.solve(**config.get_solve_kwargs())
    result.resolve(problem_spec)

    consolelog.info(f"{result.Runtime=}")
    consolelog.info(f"{result.ObjVal=}")
    consolelog.info(f"{result.ObjBound=}")
    consolelog.info(f"{result.MIPGap=}")

    master.model.close()
    for subproblem in subproblems:
        subproblem.close()

    return result
