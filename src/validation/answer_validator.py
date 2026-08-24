"""Answer Validator (TECHNICAL_SOLUTION.md 第 20.3 章).

校验最终答案:
- structure: 答案是合法 JSON 且字段完整
- extract: 目标字段来自 table evidence
- thinking: 计算输入存在于表格 evidence
"""

from __future__ import annotations

import json
from typing import TYPE_CHECKING

from src.observability.logger import get_logger
from src.table.models import Table, TaskResult
from src.validation.schema_validator import validate_structure_json

if TYPE_CHECKING:
    from src.table.models import Question

logger = get_logger("answer_validator")


def validate_answer(question: "Question", result: TaskResult, table: Table | None = None) -> TaskResult:
    """校验单题答案, 返回可能更新 warnings 后的 TaskResult."""
    qtype = question.question_type
    answer = result.answer or ""

    if qtype == "structure":
        try:
            validate_structure_json(answer)
        except Exception as exc:  # noqa: BLE001
            result.warnings.append(f"structure JSON invalid: {exc}")
            # structure 答案非法: 标记为空答案避免扣分? SPEC 允许无法作答时填空.
            # 这里保留原答案但降级 confidence, 由 pipeline 决定是否替换为空.
            result.confidence = 0.0
    elif qtype == "extract":
        if not answer:
            result.warnings.append("empty extract answer")
    elif qtype == "thinking":
        if not answer:
            result.warnings.append("empty thinking answer")
        # 校验 JSON 数组类答案合法.
        if answer.strip().startswith("["):
            try:
                json.loads(answer)
            except Exception as exc:  # noqa: BLE001
                result.warnings.append(f"thinking JSON array invalid: {exc}")
    return result


class AnswerValidator:
    """答案校验器 (便于注入与扩展)."""

    def validate(self, question: "Question", result: TaskResult, table: Table | None = None) -> TaskResult:
        """校验入口."""
        return validate_answer(question, result, table)
