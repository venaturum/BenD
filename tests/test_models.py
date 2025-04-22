from functools import lru_cache

import gurobipy as gp
import numpy as np
import pytest

MODEL_DIRECTORY = "./tests/models"

model_filenames = [
    "knapsack_lin.mps.bz2",
    "knapsack_lin_bounds.mps.bz2",
    "knapsack_lin_decomposable.mps.bz2",
    "knapsack_lin_some_zero_sub_obj.mps.bz2",
    "knapsack_lin_zero_master_obj.mps.bz2",
    "knapsack_lin_zero_sub_obj.mps.bz2",
    "knapsack_qp_decomposable.mps.bz2",
    "knapsack_qp_plus_objconst.mps.bz2",
    "knapsack_lin_max.mps.bz2",
    "knapsack_lin_bounds_max.mps.bz2",
    "knapsack_lin_decomposable_max.mps.bz2",
    "knapsack_lin_some_zero_sub_obj_max.mps.bz2",
    "knapsack_lin_zero_master_obj_max.mps.bz2",
    "knapsack_lin_zero_sub_obj_max.mps.bz2",
    "knapsack_qp_decomposable_max.mps.bz2",
    "knapsack_qp_plus_objconst_max.mps.bz2",
]


def get_model(model_filename, env):
    return gp.read(f"{MODEL_DIRECTORY}/{model_filename}", env=env)


@lru_cache
def get_gurobi_objval(model_filename, env, relax=False):
    m = gp.read(f"{MODEL_DIRECTORY}/{model_filename}", env=env)
    if relax:
        m = m.relax()
    m.params.MIPGap = 0
    m.optimize()
    return m.ObjVal


@pytest.mark.parametrize("model_filename", model_filenames)
@pytest.mark.parametrize("framework", ["callback", "iterative"])
@pytest.mark.parametrize("lpform", ["primal", "dual"])
@pytest.mark.parametrize("subreturn", ["subgradient", "duals"])
def test_model(model_filename, framework, lpform, subreturn):
    from bendee.cli import _run_simple_milp_benders

    with gp.Env() as env:
        grb_objval = get_gurobi_objval(model_filename, env=env)
        result = _run_simple_milp_benders(
            filepath=f"{MODEL_DIRECTORY}/{model_filename}",
            framework=framework,
            lpform=lpform,
            subreturn=subreturn,
            loglevel=None,
            config_path=None,
            resultfile=None,
        )
        solution = result.X
        m = get_model(model_filename, env=env)
        m.setAttr("UB", m.getVars(), solution)
        m.setAttr("LB", m.getVars(), solution)
        m.optimize()
        assert m.Status == gp.GRB.Status.OPTIMAL  # better to be feasible instead?
        assert abs(grb_objval - m.ObjVal) < 0.001


def test_callback_framework_continuous_model():
    from bendee import Config, ProblemSpec, config, solve

    with gp.Env() as env:
        model_filename = "knapsack_lin.mps.bz2"
        grb_objval = get_gurobi_objval(model_filename, env, relax=True)
        m = get_model(model_filename, env)
        inds = [v.index for v in m.getVars() if v.VType != "C"]
        m = m.relax()
        ps = ProblemSpec(m)
        ps.set_complicating_vars([v for v in m.getVars() if v.index in inds])

        config_ = Config()
        config_.sub_form = config.SubproblemLpForm.primal
        config_.sub_return = config.SubproblemReturn.duals
        config_.framework = config.Framework.callback
        Result = solve(ps, config_, env)
        assert np.isclose(grb_objval, Result.ObjVal)
