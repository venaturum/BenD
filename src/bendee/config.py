import tomllib
from enum import Enum, auto
from typing import Any, Dict


class Framework(Enum):
    callback = auto()
    iterative = auto()

    @staticmethod
    def default():
        return Framework.callback


class SubproblemLpForm(Enum):
    primal = auto()
    dual = auto()

    @staticmethod
    def default():
        return SubproblemLpForm.primal


class SubproblemReturn(Enum):
    subgradient = auto()
    duals = auto()

    @staticmethod
    def default():
        return SubproblemReturn.subgradient


class Config:
    def __init__(self, toml_path: str | None = None) -> None:
        values = self._get_dict_from_toml(toml_path)
        iterative_params = values.pop("iterative_framework_params", {})
        self.framework: Framework = values.pop("framework", Framework.default())
        self.lp_form: SubproblemLpForm = values.pop(
            "lp_form", SubproblemLpForm.default()
        )
        self.sub_return: SubproblemReturn = values.pop(
            "sub_return", SubproblemReturn.default()
        )
        self.theta_lb = iterative_params.pop("theta_lb", -10000)
        self.max_iterations: int = iterative_params.pop("max_iterations", 1000)
        self.iterative_framework_optimality_gap: float = iterative_params.pop(
            "iterative_framework_optimality_gap", 1e-8
        )
        self.iterative_framework_timelimit: float = iterative_params.pop(
            "iterative_framework_timelimit", float("inf")
        )
        self.reset_subproblem: bool = values.pop("reset_subproblem", False)
        self.env_params: dict[str, Any] = values.pop("env_params", {})
        self.master_params: dict[str, Any] = values.pop("master_params", {})
        self.subproblem_params: dict[str, Any] = values.pop("subproblem_params", {})

        if values:
            raise RuntimeError(f"Unknown config values: {', '.join(values.keys())}")

    def get_solve_kwargs(self) -> Dict:
        kwargs: dict[str, Any] = {}
        if self.framework == Framework.iterative:
            kwargs["optimality_gap"] = self.iterative_framework_optimality_gap
            kwargs["max_iterations"] = self.max_iterations
            kwargs["timelimit"] = self.iterative_framework_timelimit

        return kwargs

    def _get_dict_from_toml(self, toml_path):
        if toml_path is None:
            return {}
        with open(toml_path, "rb") as f:
            data = tomllib.load(f)
        return data


_defaults = Config()
