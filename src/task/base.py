"""任务基类与上下文 (TECHNICAL_SOLUTION.md 第 28 章).

所有 solver 共享的 SolverContext: 包含图像路径、表格候选、QwenClient、trace 等.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from src.table.models import Question, Table, TaskResult

if TYPE_CHECKING:
    from src.observability.trace import TraceContext
    from src.table.models import TableCandidate
    from src.vision.qwen_client import QwenClient


@dataclass
class SolverContext:
    """solver 运行上下文."""

    question: Question
    image_paths: list[str] = field(default_factory=list)
    candidate: "TableCandidate | None" = None
    client: "QwenClient | None" = None
    trace: "TraceContext | None" = None
    answer_format: str | None = None


class BaseSolver(ABC):
    """所有任务 solver 的基类."""

    def __init__(self, client: "QwenClient | None" = None) -> None:
        """初始化, 允许注入 QwenClient."""
        self.client = client

    @abstractmethod
    def solve(self, ctx: SolverContext, table: Table | None = None) -> TaskResult:
        """执行任务, 返回 TaskResult."""
        raise NotImplementedError

    def _empty_result(self, ctx: SolverContext, code: str, message: str) -> TaskResult:
        """构造失败/空答案结果."""
        return TaskResult(
            id=ctx.question.id,
            answer="",
            ok=False,
            error_code=code,
            error_message=message,
            warnings=[message],
        )
