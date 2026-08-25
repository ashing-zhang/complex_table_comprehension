"""Keyword Extraction Prompt (用于页面召回的关键词抽取).

通过 LLM 从问题文本中抽取带权重的语义关键词 (实体/时间/数值/概念),
配合 page_selector 进行更精准的页面召回. 失败时由正则关键词兜底.

运行指南:
    本模块不直接运行, 由 src.document.page_selector 调用 build_keyword_prompt
    构造 prompt 后通过 QwenClient.chat 发送.
"""

from __future__ import annotations

PROMPT_VERSION = "keyword_v1"

_SYSTEM = (
    "你是关键词抽取器，用于在多页文档中定位与问题相关的页面。"
    "任务：从用户问题中抽取用于页面召回的关键词。原则：\n"
    "1. 抽取专有名词（公司/产品/人名/地名/项目名）、"
    "年份/季度/月份/时段、关键数值（原样保留）、"
    "核心业务术语或表格主题词。\n"
    "2. 忽略通用问句词（什么/如何/请问/找出/计算/列出/提取/恢复/请等）。\n"
    "3. 为每个关键词给定 weight："
    "1.0 = 高优先（专有实体/具体时间/具体数值），"
    "0.5 = 中等（业务概念/表格主题），"
    "0.3 = 弱辅助（限定/修饰性词）。\n"
    "4. 若存在同义词/缩写/近义表述，请放入 aliases 数组，"
    "用于跨页面文本匹配（如 营收 -> [营收, 营业收入, 收入]）。\n"
    "5. 若问题未涉及具体可抽取实体（如纯结构题），返回空数组 []。\n"
    "6. 只输出合法 JSON 数组，元素形如："
    '{"text": str, "weight": float, "aliases": [str, ...]}，'
    "aliases 可为空数组。不要输出任何其它内容。"
)

_USER_TMPL = (
    "问题：{question}\n"
    "{hint_line}"
    "请抽取用于页面召回的关键词，按指定 JSON 数组格式输出。"
)


def build_keyword_prompt(question: str, *, table_hint: str | None = None) -> tuple[str, str]:
    """构造关键词抽取的 system + user prompt."""
    hint_line = f"表格提示：{table_hint}\n" if table_hint else ""
    return _SYSTEM, _USER_TMPL.format(question=question, hint_line=hint_line)
