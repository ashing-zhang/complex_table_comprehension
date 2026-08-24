"""Repair Prompt (TECHNICAL_SOLUTION.md 第 21 章).

当模型输出非法 JSON 或结构校验失败时, 用上次的错误信息生成修复提示.
最多 REPAIR_MAX_RETRIES = 2 次, 不无限重试.
"""

from __future__ import annotations

PROMPT_VERSION = "repair_v1"

_SYSTEM = (
    "你是 JSON 修复模型。任务：根据上次模型输出和错误信息，"
    "重新输出合法 JSON。要求：只输出 JSON 对象，不要输出任何解释或代码块标记。"
)

_USER_TMPL = (
    "上次输出：\n{raw}\n\n"
    "错误信息：\n{error}\n\n"
    "请修正上述问题，只输出合法 JSON 对象。"
)


def build_repair_prompt(raw_output: str, error_message: str) -> tuple[str, str]:
    """构造 repair 任务的 system + user prompt.

    Args:
        raw_output: 上次模型输出原文.
        error_message: 校验/解析错误描述.

    Returns:
        (system_prompt, user_prompt).
    """
    raw = raw_output[:4000]
    user = _USER_TMPL.format(raw=raw, error=error_message[:500])
    return _SYSTEM, user
