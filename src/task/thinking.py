"""Thinking Solver (TECHNICAL_SOLUTION.md 第 16, 18 章).

流程: Question -> Question Parser -> Data Locator -> Typed Values ->
      Deterministic Calculator -> Answer.
LLM 只生成计算计划, Python 完成精确计算.
"""

from __future__ import annotations

from typing import Any

from src.observability.logger import get_logger
from src.reasoning.calculator import Calculator
from src.reasoning.value_normalizer import normalize_answer_value
from src.table.models import ErrorCode, Table, TableAgentError, TaskResult
from src.task.base import BaseSolver, SolverContext
from src.vision.table_parser import TableParser

logger = get_logger("thinking_solver")


class ThinkingSolver(BaseSolver):
    """表格内容推理 solver."""

    def __init__(self, client=None, *, parser: TableParser | None = None, repair_max_retries: int = 2) -> None:
        """初始化, 可注入 TableParser 与 Calculator."""
        super().__init__(client)
        self._parser = parser or TableParser(self.client, repair_max_retries=repair_max_retries)
        self._calculator = Calculator()

    def solve(self, ctx: SolverContext, table: Table | None = None) -> TaskResult:
        """执行 thinking 任务."""
        q = ctx.question
        fmt = ctx.answer_format or q.answer_format

        try:
            plan = self._parser.parse_thinking_plan(
                image_paths=ctx.image_paths,
                question_text=q.question,
                trace=ctx.trace,
                table_hint=q.table_hint,
            )
        except TableAgentError as exc:
            logger.warning("thinking plan failed id=%s: %s", q.id, exc)
            return self._empty_result(ctx, exc.code.value, str(exc))

        # 构建 (row, col) -> 原始文本 查找表 (若 table 已解析).
        lookup: dict[tuple[int, int], str] | None = None
        if table is not None:
            lookup = {}
            for cell in table.cells:
                for r in range(cell.row, cell.row + cell.rowspan):
                    for c in range(cell.col, cell.col + cell.colspan):
                        lookup[(r, c)] = cell.text

        op = str(plan.get("operation", "")).lower()
        # 纯格式化操作 (无算术运算): 模型已在 answer_guess 中给出格式化结果, 直接采用.
        # 避免对多值 format 调用 calculator (仅返回首值) 及 Decimal→JSON 序列化失败.
        if op in ("format", "normalize") and plan.get("answer_guess"):
            logger.info("thinking id=%s: format op, using answer_guess directly", q.id)
            answer_str = normalize_answer_value(plan.get("answer_guess"), fmt)
            return TaskResult(
                id=q.id,
                answer=answer_str,
                ok=True,
                confidence=0.8,
                evidence=plan.get("inputs", []) if isinstance(plan.get("inputs"), list) else [],
                warnings=[],
            )

        # 执行确定性计算.
        try:
            result_val = self._calculator.execute_plan(plan, table_text_lookup=lookup)
        except TableAgentError as exc:
            logger.warning("thinking calc failed id=%s: %s", q.id, exc)
            # 计算失败: 退回模型给出的 answer_guess (如果有).
            guess = plan.get("answer_guess")
            if guess:
                return TaskResult(
                    id=q.id,
                    answer=normalize_answer_value(guess, fmt),
                    ok=True,
                    confidence=0.4,
                    warnings=[f"calc failed, used guess: {exc}"],
                )
            return self._empty_result(ctx, exc.code.value, str(exc))

        # 格式化最终答案.
        answer_str = normalize_answer_value(result_val, fmt)
        # 布尔类判断题 (例如 "是否达到正向 surplus"): 检查 reasoning / answer_guess.
        if fmt == "string":
            # 对是非题: 计算结果为正/负 -> 是/否等.
            text = _bool_interpretation(plan, result_val, q.question)
            if text is not None:
                answer_str = text

        # 计数类返回整数.
        if fmt == "number" and isinstance(result_val, int):
            answer_str = str(result_val)

        return TaskResult(
            id=q.id,
            answer=answer_str,
            ok=True,
            confidence=0.85,
            evidence=plan.get("inputs", []) if isinstance(plan.get("inputs"), list) else [],
            warnings=[],
        )


def _bool_interpretation(plan: dict[str, Any], result_val: Any, question: str) -> str | None:
    """对是非题做布尔解释 (例如 "是否达到正向 surplus")."""
    from src.table.normalizer import to_decimal
    from decimal import Decimal

    q = question.lower()
    if "是否" in question or "是不是" in question or "有没有" in question or "是否达到" in question:
        d = to_decimal(str(result_val)) if not isinstance(result_val, Decimal) else result_val
        if d is None:
            return None
        if d > 0:
            return "是"
        if d < 0:
            return "否"
        return "持平"
    return None
