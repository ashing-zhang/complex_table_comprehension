"""视觉解析器: 将 LLM 输出解析为结构化中间结果.

提供 JSON 提取、修复提示等工具函数, 供 table_parser 与各 solver 复用.
"""

from __future__ import annotations

import json
import re
from typing import Any

from src.observability.logger import get_logger
from src.table.models import ErrorCode, TableAgentError

logger = get_logger("vision_parser")

# 匹配 ```json ... ``` 或裸 JSON 对象/数组.
_JSON_FENCE_RE = re.compile(r"```(?:json)?\s*(.*?)\s*```", re.DOTALL)


def extract_json(text: str) -> Any:
    """从模型回复中提取 JSON.

    优先尝试整体 parse, 失败则尝试 ```json``` 代码块, 再尝试首个 {...} 或 [...].
    Raises:
        TableAgentError(INVALID_JSON): 无法解析时.
    """
    if not text:
        raise TableAgentError(ErrorCode.INVALID_JSON, "empty model output")

    # 去除思考过程常见的 <think>...</think> 包裹.
    cleaned = re.sub(r"<think>.*?</think>", "", text, flags=re.DOTALL).strip()

    # 1. 直接整体解析.
    try:
        return json.loads(cleaned)
    except Exception:
        pass

    # 2. ```json``` 代码块.
    m = _JSON_FENCE_RE.search(cleaned)
    if m:
        try:
            return json.loads(m.group(1))
        except Exception:
            pass

    # 3. 第一个 {...} 平衡块.
    obj = _extract_balanced(cleaned, "{", "}")
    if obj is not None:
        try:
            return json.loads(obj)
        except Exception:
            pass

    # 4. 第一个 [...] 平衡块.
    arr = _extract_balanced(cleaned, "[", "]")
    if arr is not None:
        try:
            return json.loads(arr)
        except Exception:
            pass

    raise TableAgentError(ErrorCode.INVALID_JSON, f"cannot parse JSON from output: {cleaned[:200]}")


def _extract_balanced(text: str, open_ch: str, close_ch: str) -> str | None:
    """提取首个括号平衡的子串."""
    start = text.find(open_ch)
    if start < 0:
        return None
    depth = 0
    in_str = False
    esc = False
    for i in range(start, len(text)):
        ch = text[i]
        if in_str:
            if esc:
                esc = False
            elif ch == "\\":
                esc = True
            elif ch == '"':
                in_str = False
            continue
        if ch == '"':
            in_str = True
            continue
        if ch == open_ch:
            depth += 1
        elif ch == close_ch:
            depth -= 1
            if depth == 0:
                return text[start : i + 1]
    return None


def safe_json_parse(text: str, default: Any = None) -> Any:
    """安全解析 JSON, 失败返回 default."""
    try:
        return extract_json(text)
    except TableAgentError:
        return default
