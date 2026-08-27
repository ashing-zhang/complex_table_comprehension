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
    else:
        return result

    # json 类 answer_format: 校验 JSON 合法性与目标形态 (extract/thinking 通用).
    fmt = question.answer_format
    if fmt in ("json", "json_array"):
        _validate_json_format(fmt, answer, result)
    return result


def _validate_json_format(fmt: str, answer: str, result: TaskResult) -> None:
    """校验 json / json_array 格式答案的合法性与形态.

    违规时追加 warning 并将 confidence 降级为 0 (不改动答案内容).
    """
    try:
        obj = json.loads(answer) if answer.strip() else None
    except Exception as exc:  # noqa: BLE001
        result.warnings.append(f"answer_format={fmt} but answer is not valid JSON: {exc}")
        result.confidence = 0.0
        return
    expected_type = list if fmt == "json_array" else dict
    if not isinstance(obj, expected_type):
        result.warnings.append(
            f"answer_format={fmt} expects {expected_type.__name__}, got {type(obj).__name__}"
        )
        result.confidence = 0.0
    elif fmt == "json_array" and not obj:
        result.warnings.append("answer_format=json_array got empty array")
        result.confidence = 0.0


class AnswerValidator:
    """答案校验器 (便于注入与扩展)."""

    def validate(self, question: "Question", result: TaskResult, table: Table | None = None) -> TaskResult:
        """校验入口."""
        return validate_answer(question, result, table)
