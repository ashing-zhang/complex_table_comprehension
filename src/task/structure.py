"""Structure Solver (TECHNICAL_SOLUTION.md 第 11 章).

流程: image -> Qwen -> JSON -> grid validation -> structure answer.
"""

from __future__ import annotations

import json

from src.observability.logger import get_logger
from src.table.grid import validate_grid
from src.table.models import ErrorCode, Table, TableAgentError
from src.task.base import BaseSolver, SolverContext
from src.vision.table_parser import TableParser

logger = get_logger("structure_solver")


class StructureSolver(BaseSolver):
    """表格结构恢复 solver."""

    def __init__(self, client=None, *, parser: TableParser | None = None, repair_max_retries: int = 2) -> None:
        """初始化, 可注入 TableParser."""
        super().__init__(client)
        self._parser = parser or TableParser(self.client, repair_max_retries=repair_max_retries)

    def solve(self, ctx: SolverContext, table: Table | None = None) -> "TaskResult":
        """执行 structure 任务.

        若传入已解析的 table (来自 Canonical Table 复用), 直接校验 + 输出;
        否则调用视觉模型重新解析.
        """
        from src.table.models import TaskResult

        q = ctx.question
        # 解析题目中的局部范围提示.
        local_hint = _extract_local_hint(q.question)

        try:
            if table is None:
                table = self._parser.parse_structure(
                    image_paths=ctx.image_paths,
                    question_text=q.question,
                    trace=ctx.trace,
                    local_hint=local_hint,
                )
        except TableAgentError as exc:
            logger.warning("structure parse failed id=%s: %s", q.id, exc)
            return self._empty_result(ctx, exc.code.value, str(exc))

        # grid 校验 (结构合法性).
        validation = validate_grid(table)
        if not validation.ok:
            msg = "structure grid invalid: " + "; ".join(validation.issues[:5])
            logger.warning("id=%s %s", q.id, msg)
            # grid 校验失败不直接抛弃, 仍输出但标记 warning, 由 validator 兜底.
            return TaskResult(
                id=q.id,
                answer=json.dumps(table.to_structure_json(), ensure_ascii=False),
                ok=True,
                confidence=0.5,
                warnings=[msg],
            )

        answer_json = json.dumps(table.to_structure_json(), ensure_ascii=False)
        return TaskResult(
            id=q.id,
            answer=answer_json,
            ok=True,
            confidence=0.9,
            evidence=[c.to_dict() for c in table.cells[:20]],
            warnings=[],
        )


def _extract_local_hint(question: str) -> str | None:
    """从题目文本中提取局部结构范围提示 (例如 "前 1 行前 1 列")."""
    import re

    m = re.search(r"(前\s*\d+\s*[行列][^。]*)", question)
    return m.group(0).strip() if m else None
