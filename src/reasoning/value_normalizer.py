"""答案值归一化 (TECHNICAL_SOLUTION.md 第 17, 19 章).

将 LLM/计算器的中间结果格式化为最终 submission answer 字符串.
- number: 去千分位逗号
- percent: 12.5% 形式
- json / json_array: 序列化为 JSON 字符串, 并强制目标形态
  (json -> 对象; json_array -> 元素为键值对象的数组),
  非法输入包装为 {"answer": <文本>} 兜底, 保证输出恒为合法 JSON.
- string: 原样 (去首尾空白)

运行指南: 本模块为纯函数库, 由 task 层 solver 调用, 无需单独运行.
"""

from __future__ import annotations

import json
import re
from decimal import Decimal
from typing import Any

from src.table.normalizer import format_number, to_decimal

# 兜底拆分多值自由文本时的分隔符.
_JSON_ARRAY_SPLIT_RE = re.compile(r"[,，、;；\n]+")


def _to_decimal(value: Any) -> Decimal | None:
    """将任意值转为 Decimal (复用 table.normalizer.to_decimal)."""
    if isinstance(value, Decimal):
        return value
    if isinstance(value, (int, float)):
        return Decimal(str(value))
    return to_decimal(str(value))


def _wrap_scalar(value: Any) -> dict[str, Any]:
    """将标量包装为单一键值对象 (键固定为 answer)."""
    if isinstance(value, (Decimal, int, float)):
        return {"answer": format_number(value)}
    text = str(value).strip()
    if not text:
        return {"answer": ""}
    dec = to_decimal(text.replace(",", ""))
    if dec is not None:
        return {"answer": format_number(dec)}
    return {"answer": text}


def _coerce_to_object(value: Any) -> Any:
    """将值归一为 JSON 对象形态."""
    if isinstance(value, dict):
        return value
    return _wrap_scalar(value)


def _coerce_to_array(value: Any) -> list[Any]:
    """将值归一为 JSON 数组形态 (元素为键值对象, 符合 SPEC 答案规范)."""
    if isinstance(value, list):
        return [_coerce_to_object(v) for v in value]
    if isinstance(value, dict):
        return [value]
    return [_wrap_scalar(value)]


def _coerce_json_payload(value: Any, fmt: str) -> Any:
    """将中间结果强制转换为目标 JSON 形态.

    Args:
        value: LLM/计算器给出的中间结果 (str/list/dict/标量).
        fmt: 目标格式 ("json" 或 "json_array").

    Returns:
        可直接 json.dumps 的对象.
    """
    if isinstance(value, str):
        text = value.strip()
        try:
            parsed = json.loads(text)
        except Exception:
            # 非法 JSON 自由文本: json_array 时尝试按分隔符拆分为多值, 否则整体包装.
            if fmt == "json_array":
                parts = [p.strip() for p in _JSON_ARRAY_SPLIT_RE.split(text) if p.strip()]
                return _coerce_to_array(parts if parts else text)
            return _coerce_to_object(text)
        if fmt == "json_array":
            return _coerce_to_array(parsed)
        return _coerce_to_object(parsed)

    if fmt == "json_array":
        return _coerce_to_array(value)
    return _coerce_to_object(value)


def normalize_answer_value(value: Any, answer_format: str | None = None) -> str:
    """将中间结果归一为最终 answer 字符串."""
    if value is None:
        return ""

    fmt = (answer_format or "").strip().lower()

    # json / json_array: 强制目标形态后序列化为 JSON 字符串.
    if fmt in ("json", "json_array"):
        payload = _coerce_json_payload(value, fmt)
        # default=str: Decimal 等非原生 JSON 类型转为 str, 避免 TypeError.
        return json.dumps(payload, ensure_ascii=False, default=str)

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
