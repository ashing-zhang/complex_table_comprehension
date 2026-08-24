"""Extract Prompt (TECHNICAL_SOLUTION.md 第 25 章).

先定位 (文件->页->表->表头->行/列->单元格), 再输出答案.
要求模型返回 evidence + answer.
"""

from __future__ import annotations

PROMPT_VERSION = "extract_v1"

_SYSTEM = (
    "你是复杂表格内容提取模型。任务：从输入表格图像中抽取指定内容。"
    "原则：\n"
    "1. 先定位：文件 -> 页面 -> 表格 -> 表头 -> 行/列 -> 单元格，再输出答案。\n"
    "2. 禁止根据常识补全表格中不存在的数据。\n"
    "3. 文本答案保留原始含义，可去除多余空格和换行。\n"
    "4. 数字答案去除千分位逗号（例如 138000，不要 138,000）。\n"
    "5. 如果答案是单个值，answer 字段填写该值的字符串形式。\n"
    "6. 如果答案是一行/一列/一个区域，answer 字段填写 JSON 数组，"
    "数组元素使用键值对象，键为列标题或行标题。\n"
    "7. 若某些值在表格中为空，填写空字符串。\n"
    "8. 不要在答案中写“根据表格可知”“答案是”等说明性文字。\n"
    "9. 只输出合法 JSON，格式为："
    '{"evidence": [{"row": int, "col": int, "text": str}], "answer": str | list}.'
)

_USER_TMPL = (
    "题目：{question}\n"
    "{hint_line}"
    "请从图像中的表格提取指定内容，先给出 evidence 再给出 answer。\n"
    "只输出 JSON 对象，不要输出任何其它内容。"
)


def build_extract_prompt(question: str, *, table_hint: str | None = None) -> tuple[str, str]:
    """构造 extract 任务的 system + user prompt."""
    hint_line = f"表格提示：{table_hint}\n" if table_hint else ""
    return _SYSTEM, _USER_TMPL.format(question=question, hint_line=hint_line)
