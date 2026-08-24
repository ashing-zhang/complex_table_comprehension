"""Schema 校验器 (TECHNICAL_SOLUTION.md 第 20.1 章).

检查 JSON 是否合法, 字段是否存在且类型正确.
"""

from __future__ import annotations

import json
from typing import Any

from src.table.models import ErrorCode, TableAgentError


def validate_structure_json(answer: str) -> dict[str, Any]:
    """校验 structure 题型 answer 是否为合法 JSON 并含必填字段.

    Returns:
        解析后的 dict.

    Raises:
        TableAgentError(STRUCTURE_INVALID / INVALID_JSON).
    """
    if not answer:
        raise TableAgentError(ErrorCode.INVALID_JSON, "empty structure answer")
    try:
        data = json.loads(answer)
    except Exception as exc:  # noqa: BLE001
        raise TableAgentError(ErrorCode.INVALID_JSON, f"structure answer not valid JSON: {exc}") from exc

    if not isinstance(data, dict):
        raise TableAgentError(ErrorCode.STRUCTURE_INVALID, "structure answer is not an object")

    for key in ("row_count", "col_count", "cells"):
        if key not in data:
            raise TableAgentError(ErrorCode.STRUCTURE_INVALID, f"structure answer missing key: {key}")

    if not isinstance(data["row_count"], int) or not isinstance(data["col_count"], int):
        raise TableAgentError(ErrorCode.STRUCTURE_INVALID, "row_count/col_count must be int")
    if not isinstance(data["cells"], list):
        raise TableAgentError(ErrorCode.STRUCTURE_INVALID, "cells must be a list")

    for i, c in enumerate(data["cells"]):
        if not isinstance(c, dict):
            raise TableAgentError(ErrorCode.STRUCTURE_INVALID, f"cell {i} not an object")
        for k in ("text", "row", "col", "rowspan", "colspan"):
            if k not in c:
                raise TableAgentError(ErrorCode.STRUCTURE_INVALID, f"cell {i} missing key: {k}")
        if not isinstance(c["row"], int) or not isinstance(c["col"], int):
            raise TableAgentError(ErrorCode.STRUCTURE_INVALID, f"cell {i} row/col must be int")
        if not isinstance(c["rowspan"], int) or not isinstance(c["colspan"], int):
            raise TableAgentError(ErrorCode.STRUCTURE_INVALID, f"cell {i} rowspan/colspan must be int")
        if not isinstance(c["text"], str):
            raise TableAgentError(ErrorCode.STRUCTURE_INVALID, f"cell {i} text must be str")
    return data


def validate_task_result_schema(result: Any) -> bool:
    """校验 TaskResult 基本 schema (answer 必须为 str)."""
    if not hasattr(result, "answer"):
        return False
    if not isinstance(result.answer, str):
        return False
    return True
