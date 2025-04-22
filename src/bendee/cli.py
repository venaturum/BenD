import logging
from textwrap import dedent

import click
import gurobipy as gp

from bendee.api import solve
from bendee.config import Config, Framework, SubproblemLpForm, SubproblemReturn
from bendee.solution import Result
from bendee.staging import ProblemSpec

logging.basicConfig(level=logging.ERROR)


@click.group()
@click.version_option()
def cli():
    "Command line interface for BenD ('bendee') package"


@cli.command(name="config_example")
def print_config():
    print(
        dedent("""
        # Example config.toml contents
               
        # framework = "callback" or "iterative"
        framework = "callback"

        # lp_form = "primal" or "dual"
        lp_form = "primal"

        # sub_return = "subgradient" or "duals"
        sub_return = "subgradient"

        # should subproblem models be reset before solves?
        reset_subproblem = false

               
        [iterative_framework_params]
               
        # lower bound on theta (proxy for subproblem objective)
        theta_lb = -10000

        # max iterations for iterative framework
        max_iterations = 1000

        # termination criteria for iterative framework
        iterative_framework_optimality_gap = 1e-8

        # timelimit termination criteria (seconds) for iterative framework
        iterative_framework_timelimit = 100

               
        [env_params]
        WLSACCESSID = "1234abcd-1234-abcd-1234-abcd1234abcd"
        WLSSECRET = "abcd1234-abcd-1234-abcd-1234abcd1234"
        LICENSEID = 123456

        [master_params]
        MIPFocus = 1

        [subproblem_params]
        Presolve = 1
        """)
    )


@cli.command(name="simple_milp")
@click.argument(
    "filepath",
    type=click.Path(exists=True),
)
@click.option(
    "-f",
    "--framework",
    type=click.Choice([item.name for item in Framework]),
    default=Framework.default().name,
    help="Which framework to use",
)
@click.option(
    "-l",
    "--lpform",
    type=click.Choice([item.name for item in SubproblemLpForm]),
    default=SubproblemLpForm.default().name,
    help="Subproblem form",
)
@click.option(
    "-r",
    "--subreturn",
    type=click.Choice([item.name for item in SubproblemReturn]),
    default=SubproblemReturn.default().name,
    help="Subproblem return type",
)
@click.option(
    "--loglevel",
    type=str,
    default=None,
    help="Logging level",
)
@click.option(
    "--config",
    type=click.Path(exists=True),
    default=None,
    help="Filepath for config toml file",
)
@click.option(
    "--ResultFile",
    type=str,
    default=None,
    help="Use to write .mst or .sol file",
)
def run_simple_milp_benders(
    filepath: str,
    framework: str,
    lpform: str,
    subreturn: str,
    loglevel: str | None,
    config: str | None,
    resultfile: str | None,
):
    _run_simple_milp_benders(
        filepath, framework, lpform, subreturn, loglevel, config, resultfile
    )


def _run_simple_milp_benders(
    filepath: str,
    framework: str,
    lpform: str,
    subreturn: str,
    loglevel: str | None,
    config_path: str | None,
    resultfile: str | None,
) -> Result:
    "Run a simple milp benders"
    config = Config(config_path)

    if loglevel:
        logging_level = {
            "debug": logging.DEBUG,
            "info": logging.INFO,
        }[loglevel.lower()]
        logging.basicConfig(level=logging_level, force=True)

    with gp.Env(params=config.env_params) as env, gp.read(filepath, env) as m:
        logging.debug("Modelfile read")
        ps = ProblemSpec(m)
        logging.debug("ProblemSpec constructed")
        ps.set_complicating_vars([v for v in m.getVars() if v.VType != "C"])

        config.framework = Framework[framework]
        config.lp_form = SubproblemLpForm[lpform]
        config.sub_return = SubproblemReturn[subreturn]
        result: Result = solve(ps, config, env)
        if resultfile:
            result.write(resultfile)
        return result
