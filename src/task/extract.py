"""Extract Solver (TECHNICAL_SOLUTION.md 第 13 章).

流程: Question -> Semantic Locator -> Target Row/Column/Cell -> Value Extractor.
模型先定位再输出 evidence + answer, 程序格式化为最终答案.
"""

from __future__ import annotations

import json
from typing import Any

from src.observability.logger import get_logger
from src.reasoning.value_normalizer import normalize_answer_value
from src.table.models import ErrorCode, Table, TableAgentError, TaskResult
from src.task.base import BaseSolver, SolverContext
from src.vision.table_parser import TableParser

logger = get_logger("extract_solver")


class ExtractSolver(BaseSolver):
    """表格内容提取 solver."""

    def __init__(self, client=None, *, parser: TableParser | None = None, repair_max_retries: int = 2) -> None:
        """初始化, 可注入 TableParser."""
        super().__init__(client)
        self._parser = parser or TableParser(self.client, repair_max_retries=repair_max_retries)

    def solve(self, ctx: SolverContext, table: Table | None = None) -> TaskResult:
        """执行 extract 任务."""
        q = ctx.question
        fmt = ctx.answer_format or q.answer_format

        try:
            data = self._parser.parse_extract_raw(
                image_paths=ctx.image_paths,
                question_text=q.question,
                trace=ctx.trace,
                table_hint=q.table_hint,
            )
        except TableAgentError as exc:
            logger.warning("extract parse failed id=%s: %s", q.id, exc)
            return self._empty_result(ctx, exc.code.value, str(exc))

        answer_raw = data.get("answer")
        evidence = data.get("evidence") or []
        if not isinstance(evidence, list):
            evidence = []

        # 格式化最终答案.
        if isinstance(answer_raw, (list, dict)):
            # 多值/区域: 输出 JSON 数组 (SPEC 要求数组元素为键值对象).
            if isinstance(answer_raw, dict):
                # 单对象: 包成数组以符合 json_array 格式? 按 answer_format 决定.
                if fmt == "json_array":
                    payload: Any = [answer_raw]
                else:
                    payload = answer_raw
            else:
                payload = answer_raw
            answer_str = normalize_answer_value(payload, fmt or "json_array")
        elif answer_raw is None:
            answer_str = ""
        else:
            answer_str = normalize_answer_value(answer_raw, fmt)

        # 数字格式化时去除千分位逗号.
        if fmt == "number":
            answer_str = answer_str.replace(",", "")

        return TaskResult(
            id=q.id,
            answer=answer_str,
            ok=True,
            confidence=0.85,
            evidence=evidence if isinstance(evidence, list) else [],
            warnings=[],
        )
