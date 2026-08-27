"""答案值归一化 (TECHNICAL_SOLUTION.md 第 17, 19 章).

将 LLM/计算器的中间结果格式化为最终 submission answer 字符串.
- number: 去千分位逗号
- percent: 12.5% 形式
- json / json_array: 序列化为 JSON 字符串
- string: 原样 (去首尾空白)
"""

from __future__ import annotations

import json
from decimal import Decimal
from typing import Any

from src.table.normalizer import format_number, to_decimal


def _to_decimal(value: Any) -> Decimal | None:
    """将任意值转为 Decimal (复用 table.normalizer.to_decimal)."""
    if isinstance(value, Decimal):
        return value
    if isinstance(value, (int, float)):
        return Decimal(str(value))
    return to_decimal(str(value))


def normalize_answer_value(value: Any, answer_format: str | None = None) -> str:
    """将中间结果归一为最终 answer 字符串."""
    if value is None:
        return ""

    fmt = (answer_format or "").strip().lower()

    # json / json_array: 序列化为 JSON 字符串.
    if fmt in ("json", "json_array"):
        if isinstance(value, str):
            # 已经是 JSON 字符串: 确保合法.
            try:
                obj = json.loads(value)
                return json.dumps(obj, ensure_ascii=False, default=str)
            except Exception:
                return value
        # default=str: Decimal 等非原生 JSON 类型转为 str, 避免 TypeError.
        return json.dumps(value, ensure_ascii=False, default=str)

    # number / number-like.
    if fmt == "number":
        if isinstance(value, (Decimal, int, float)):
            return format_number(value, output_format="number")
        # 字符串数字: 去千分位逗号.
        s = str(value).strip().replace(",", "")
        return s

    # percent: 内部分数 (0.125) -> "12.5%".
    if fmt in ("percent", "percentage"):
        d = _to_decimal(value)
        if d is None:
            return str(value).strip()
        return format_number(d * 100, output_format="number") + "%"

    # string / 默认.
    if isinstance(value, (Decimal, int, float)):
        return format_number(value)
    if isinstance(value, (list, dict)):
        return json.dumps(value, ensure_ascii=False, default=str)
    return str(value).strip()
