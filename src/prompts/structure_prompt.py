"""Structure Prompt (TECHNICAL_SOLUTION.md 第 24 章).

要求模型输出合法 JSON: row_count / col_count / cells[].
"""

from __future__ import annotations

# Prompt 版本号, 用于缓存键失效 (TECHNICAL_SOLUTION.md 第 47 章).
PROMPT_VERSION = "structure_v1"

_SYSTEM = (
    "你是复杂表格结构恢复模型。任务：根据输入表格图像恢复逻辑表格结构。"
    "要求：\n"
    "1. row/col 从 0 开始编号。\n"
    "2. 每个真实单元格只输出一次。\n"
    "3. 横向合并使用 colspan，纵向合并使用 rowspan。\n"
    "4. 被合并覆盖的位置不要输出空单元格。\n"
    "5. row_count 和 col_count 表示完整逻辑表格尺寸。\n"
    "6. 如果题目要求局部结构，只输出指定范围内的真实单元格，"
    "但 row_count 和 col_count 仍填写完整表格的逻辑行列数，"
    "row/col 仍按完整表格从 0 开始编号，rowspan/colspan 仍表示该单元格在完整表格中的真实合并范围。\n"
    "7. 不要添加图像中不存在的文本。\n"
    "8. 不要输出解释性文字。\n"
    "9. 只输出合法 JSON，格式为："
    '{"row_count": int, "col_count": int, "cells": ['
    '{"text": str, "row": int, "col": int, "rowspan": int, "colspan": int}]}。'
)

_USER_TMPL = (
    "题目：{question}\n"
    "{local_line}"
    "请仔细观察图像中的表格，恢复其逻辑结构。\n"
    "只输出 JSON 对象，不要输出任何其它内容。"
)


def build_structure_prompt(question: str, *, local_hint: str | None = None) -> tuple[str, str]:
    """构造 structure 任务的 system + user prompt.

    Args:
        question: 题目文本.
        local_hint: 局部结构提示 (例如 "前 1 行前 1 列").

    Returns:
        (system_prompt, user_prompt).
    """
    local_line = f"局部范围说明：{local_hint}\n" if local_hint else ""
    user = _USER_TMPL.format(question=question, local_line=local_line)
    return _SYSTEM, user
