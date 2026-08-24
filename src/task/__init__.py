"""任务子包: structure / extract / thinking 三类 solver."""

from src.task.base import BaseSolver, SolverContext
from src.task.extract import ExtractSolver
from src.task.structure import StructureSolver
from src.task.thinking import ThinkingSolver

__all__ = ["BaseSolver", "SolverContext", "StructureSolver", "ExtractSolver", "ThinkingSolver"]
