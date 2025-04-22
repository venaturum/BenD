<p align="center">
  <a href="https://github.com/venaturum/BenD">
    <img src="./docs/img/BenD.svg" title="BenD logo" alt="BenD logo">
  </a>
</p>

## Overview

BenD (a.k.a "bendee") is a Python package implementing Bender's Decomposition for models built with Gurobi.  The design is flexible enough a to accommodate min or max objectives, integer variables, quadratic expressions, bounded variables - all that is required is that the subproblems are linear programs.

This package is not intended to be used in production, but rather as a tool for experimentation and learning.

Features include:

- Flexible usage via CLI or API
- User can specify the "complicating variables" (via API) or implicitly assume these are the integer variables
- User can form multiple subproblems based on disconnected groups of "non-complicating variables"
- Choice of framework: the traditional iterative approach, or the modern approach using callbacks
- Choide of LP subproblem form: either primal or dual form
- Choice of calculating cuts: via dual values or subgradients
- Exposing Gurobi parameters, including those used for licensing 
- Solution files can be written out as .sol or .mst files


## Installation

BenD can be installed from GitHub.

To install the latest version from PyPI:

```bash
python -m pip install git+https://github.com/venaturum/BenD.git
```

## Command line usage

```console
Usage: bendee [OPTIONS] COMMAND [ARGS]...

  Command line interface for BenD ('bendee') package

Options:
  --version  Show the version and exit.
  --help     Show this message and exit.

Commands:
  config_example
  simple_milp
```

### simple_milp subcommand

This subcommand can be used when the complicating variables are the integer variables in a program, and only one subproblem is required.  For finer control the API must be used.

```console
Usage:

    Usage: bendee simple_milp [OPTIONS] FILEPATH

    Run a simple milp benders

    Options:
    -f, --framework [callback|iterative]
                                  Which framework to use
    -l, --lpform [primal|dual]    Subproblem form
    -r, --subreturn [subgradient|duals]
                                  Subproblem return type
    -l, --loglevel TEXT           Logging level
    --config PATH                 Filepath for config toml file
    --ResultFile TEXT             Use to write .mst or .sol file
    --help                        Show this message and exit.
```

## API usage

Example:

```python
import gurobipy as gp
import bendee as bd

with gp.Env() as env:
    model = gp.read("/path/to/model.mps.bz2", env=env)
    spec = bd.ProblemSpec(model)
    spec.set_complicating_vars([v for v in model.getVars() if v.VType != "C"])

    new_config = bd.Config()
    new_config.sub_form = bd.config.SubproblemLpForm.primal
    new_config.sub_return = bd.config.SubproblemReturn.duals
    new_config.framework = bd.config.Framework.callback
    new_config.timelimit = 10
    result = bd.solve(spec, new_config, env)
    result.write("solution.sol")
```

Example with multiple subproblems:

```python
import gurobipy as gp
import bendee as bd

with gp.Env() as env:
    model = gp.read("path/to/model.lp", env=env)

    # When integer variables are fixed the subproblem can be decomposed into 8 different LPs.
    # Variable groups can be determined by name in this example.
    var_groups = [[],[],[],[],[],[],[],[]]
    for v in model.getVars():
        if v.varname.startswith("var_"):
            var_groups[int(v.varname[4])].append(v)

    spec = bd.ProblemSpec(model)
    spec.set_complicating_vars([v for v in model.getVars() if v.VType != "C"])

    for group in var_groups:
        spec.add_non_complicating_vars(group)

    new_config = bd.Config()
    new_config.sub_form = bd.config.SubproblemLpForm.dual
    new_config.sub_return = bd.config.SubproblemReturn.subgradient
    new_config.framework = bd.config.Framework.iterative
    new_config.timelimit = 10
    Result = bd.solve(spec, new_config, env)
```

## Config files

Config files should be in [toml format](https://toml.io/en/) and can be used from both CLI or API.

They allow control over finer details of the algorithm, including termination criteria for the iterative approach.

Example:

```
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
```

## Versioning

[SemVer](http://semver.org/) is used by `bendee` for versioning releases.  
For versions available, see the [tags on this repository](https://github.com/venaturum/BenD/tags).

## License

See [License](LICENSE)