"""题意解析 (TECHNICAL_SOLUTION.md 第 13 章).

从自然语言问题中抽取意图: 目标字段、行/列过滤、输出形态.
供 extract / thinking solver 使用.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field


@dataclass
class QuestionIntent:
    """题目意图."""

    raw: str
    operation: str | None = None
    keywords: list[str] = field(default_factory=list)
    is_count: bool = False
    is_sum: bool = False
    is_filter: bool = False
    is_sort: bool = False
    is_max: bool = False
    is_min: bool = False
    is_ratio: bool = False
    is_growth: bool = False
    is_format: bool = False
    output_format: str | None = None


_OP_KEYWORDS: dict[str, list[str]] = {
    "sum": ["合计", "总和", "加总", "求和", "总额", "总金额", "总数", "总共"],
    "subtract": ["差", "减", "减去", "比...少", "减少"],
    "multiply": ["乘积", "乘", "相乘"],
    "divide": ["除", "除以", "商"],
    "ratio": ["比例", "占比", "比率", "比重"],
    "growth_rate": ["增长率", "增速", "增幅", "增长", "同比", "环比"],
    "filter": ["筛选", "满足", "条件", "属于", "包含", "是"],
    "sort": ["排序", "从大到小", "从小到大", "降序", "升序"],
    "argmax": ["最大", "最高", "最多"],
    "argmin": ["最小", "最低", "最少"],
    "count": ["几个", "多少个", "数量", "几项", "项数"],
    "format": ["格式", "归一", "标准化", "转换"],
}


def parse_question_intent(question: str) -> QuestionIntent:
    """从问题文本抽取意图."""
    q = (question or "").strip()
    intent = QuestionIntent(raw=q)

    # 关键词命中 -> operation.
    for op, kws in _OP_KEYWORDS.items():
        for kw in kws:
            if kw in q:
                if op == "sum":
                    intent.is_sum = True
                elif op == "subtract":
                    intent.operation = "subtract" if intent.operation is None else intent.operation
                elif op == "multiply":
                    intent.operation = "multiply" if intent.operation is None else intent.operation
                elif op == "divide":
                    intent.operation = "divide" if intent.operation is None else intent.operation
                elif op == "ratio":
                    intent.is_ratio = True
                    intent.operation = "ratio" if intent.operation is None else intent.operation
                elif op == "growth_rate":
                    intent.is_growth = True
                    intent.operation = "growth_rate" if intent.operation is None else intent.operation
                elif op == "filter":
                    intent.is_filter = True
                elif op == "sort":
                    intent.is_sort = True
                    intent.operation = "sort" if intent.operation is None else intent.operation
                elif op == "argmax":
                    intent.is_max = True
                    intent.operation = "argmax" if intent.operation is None else intent.operation
                elif op == "argmin":
                    intent.is_min = True
                    intent.operation = "argmin" if intent.operation is None else intent.operation
                elif op == "count":
                    intent.is_count = True
                    intent.operation = "count" if intent.operation is None else intent.operation
                elif op == "format":
                    intent.is_format = True
                    intent.operation = "format" if intent.operation is None else intent.operation
                break

    # 默认 operation: count 类问题优先.
    if intent.is_count:
        intent.operation = "count"
    elif intent.is_sum:
        intent.operation = "sum"
    elif intent.operation is None:
        # 没有命中关键词, 视为 extract / 简单问答.
        intent.operation = None

    # 关键词抽取: 中文 >=2 字符的片段, 供语义定位使用.
    seen: set[str] = set()
    for m in re.finditer(r"[\u4e00-\u9fa5A-Za-z]{2,}", q):
        w = m.group(0)
        if w not in seen and w not in {"什么", "多少", "怎么", "如何", "请问", "提取", "计算", "恢复", "列出"}:
            seen.add(w)
            intent.keywords.append(w)

    return intent
