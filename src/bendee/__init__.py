import logging

from bendee.api import solve
from bendee.config import Config
from bendee.staging import ProblemSpec

consolelog = logging.getLogger("consolelog")
handler = logging.StreamHandler()
handler.setFormatter(logging.Formatter("%(message)s"))
consolelog.addHandler(handler)
consolelog.setLevel(level=logging.INFO)
formatter = logging.Formatter("%(message)s")  # Only show the actual message


logging.getLogger("gurobipy").propagate = False

__all__ = ["solve", "Config", "ProblemSpec"]
