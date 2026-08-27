"""Thinking Prompt (TECHNICAL_SOLUTION.md 第 26 章).

模型只负责生成计算计划, Python 执行计算, 显著降低幻觉计算.
支持按 answer_format 注入结构化答案要求 (json / json_array).

运行指南: 由 src.vision.table_parser 调用, 无需单独运行.
"""

from __future__ import annotations

PROMPT_VERSION = "thinking_v1"

_SYSTEM = (
    "你是复杂表格内容推理模型。任务：先定位相关数据，再生成计算计划。"
    "原则：\n"
    "1. 你不要直接进行数值计算，只输出计算计划，由后端程序执行计算。\n"
    "2. 计算计划包括 operation 与 inputs；inputs 中每个元素必须给出 row/col 坐标"
    "（0-based）以及原始 text 值，便于程序校验。\n"
    "3. 支持的 operation: sum / subtract / multiply / divide / ratio / growth_rate / "
    "filter / sort / argmax / argmin / count / format。\n"
    "4. 如果需要先定位再计算，可在 plan 字段中给出多步操作数组。\n"
    "5. 数字答案去除千分位逗号；百分比、日期、金额按题目要求格式化。\n"
    "6. 只输出合法 JSON，格式为："
    '{"operation": str, "inputs": [{"row": int, "col": int, "text": str}], '
    '"output_format": str, "reasoning": str, "answer_guess": str}。'
    "其中 answer_guess 仅供程序参考，最终答案由程序计算后确定。"
)

_USER_TMPL = (
    "题目：{question}\n"
    "{hint_line}"
    "{fmt_line}"
    "请定位表格中相关数据并生成计算计划。\n"
    "只输出 JSON 对象，不要输出任何其它内容。"
)

# 按 answer_format 注入的结构化答案指令.
_FORMAT_INSTRUCTIONS: dict[str, str] = {
    "json_array": (
        '答案格式要求：最终答案必须是 JSON 数组，数组元素为简单键值对象'
        '（示例：[{"月份": "1月", "销售总额": "12000"}]）。'
        '请在计划中额外提供 "answer" 字段直接承载该 JSON 数组，'
        "键名使用表格中的语义名称（如列标题、期间名称），不要输出说明性文字。\n"
    ),
    "json": (
        "答案格式要求：最终答案必须是 JSON 对象。"
        '请在计划中额外提供 "answer" 字段直接承载该 JSON 对象，'
        "键名使用表格中的语义名称（如列标题、行标题），不要输出说明性文字。\n"
    ),
}


def build_thinking_prompt(
    question: str,
    *,
    table_hint: str | None = None,
    answer_format: str | None = None,
) -> tuple[str, str]:
    """构造 thinking 任务的 system + user prompt.

    Args:
        question: 题目文本.
        table_hint: 表格提示.
        answer_format: 题目要求的答案格式 (json/json_array 时注入结构化指令).

    Returns:
        (system, user) 提示词二元组.
    """
    hint_line = f"表格提示：{table_hint}\n" if table_hint else ""
    fmt_key = (answer_format or "").strip().lower()
    fmt_line = _FORMAT_INSTRUCTIONS.get(fmt_key, "")
    return _SYSTEM, _USER_TMPL.format(question=question, hint_line=hint_line, fmt_line=fmt_line)
