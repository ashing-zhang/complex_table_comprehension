"""页面定位 (TECHNICAL_SOLUTION.md 第 8 章).

召回阶段: 优先显式页码 -> table_hint / 关键词 -> top-k pages.
宁可多召回, 不过早过滤.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import TYPE_CHECKING

from src.observability.logger import get_logger

if TYPE_CHECKING:
    from src.table.models import Document, Question

logger = get_logger("page_selector")


@dataclass
class PageCandidate:
    """页面候选."""

    page_index: int
    score: float


_PAGE_NUM_RE = re.compile(r"第\s*([0-9０-９]+)\s*页")
# 支持 "第3页到第4页" / "第3至4页" / "第3-4页".
_RANGE_RE = re.compile(r"第\s*([0-9０-９]+)\s*页?\s*(?:到|至|[-~])\s*第?\s*([0-9０-９]+)\s*页")


def _to_int_digit(s: str) -> int:
    """将全角/半角数字串解析为 int."""
    return int(s.translate(str.maketrans("０１２３４５６７８９", "0123456789")))


def extract_explicit_pages(question_text: str) -> list[int] | None:
    """从题目文本中提取显式页码 (0-based).

    支持 "第 3 页到第 4 页" / "第 3-4 页" / "第 3 页".
    返回 None 表示题目未显式指定页码.
    """
    rng = _RANGE_RE.search(question_text)
    if rng:
        a = _to_int_digit(rng.group(1))
        b = _to_int_digit(rng.group(2))
        if a > b:
            a, b = b, a
        return [i - 1 for i in range(a, b + 1) if i >= 1]
    single = _PAGE_NUM_RE.search(question_text)
    if single:
        n = _to_int_digit(single.group(1))
        if n >= 1:
            return [n - 1]
    return None


def select_pages(document: "Document", question: "Question", *, top_k: int = 5) -> list[PageCandidate]:
    """选择候选页面.

    策略:
    1. 题目显式页码 -> 直接优先返回这些页 (按顺序).
    2. 否则: 用 table_hint / question 关键词在页面文本中匹配打分, 取 top_k.
    3. 单页文档直接返回该页.

    Args:
        document: 已加载的文档.
        question: 题目.
        top_k: 召回上限.

    Returns:
        PageCandidate 列表 (按 score 降序).
    """
    pages = document.pages
    if not pages:
        return []

    if len(pages) == 1:
        return [PageCandidate(page_index=0, score=1.0)]

    explicit = extract_explicit_pages(question.question)
    if explicit:
        result = []
        seen = set()
        for p in explicit:
            if 0 <= p < len(pages) and p not in seen:
                result.append(PageCandidate(page_index=p, score=1.0))
                seen.add(p)
        if result:
            # 补充一两页相邻页面作为召回, 防止跨页表格遗漏.
            for p in explicit:
                for nb in (p - 1, p + 1):
                    if 0 <= nb < len(pages) and nb not in seen:
                        result.append(PageCandidate(page_index=nb, score=0.5))
                        seen.add(nb)
            return result[: max(top_k, len(explicit))]

    # 基于关键词的软召回.
    keywords: list[str] = []
    if question.table_hint:
        keywords.append(question.table_hint.strip())
    # 从 question 中抽取长度 >=2 的中文词片段.
    for m in re.finditer(r"[\u4e00-\u9fa5]{2,}", question.question):
        s = m.group(0)
        if s not in keywords and len(s) >= 2:
            keywords.append(s)

    scored: list[PageCandidate] = []
    for i, page in enumerate(pages):
        text = page.text or ""
        if not text and not keywords:
            scored.append(PageCandidate(page_index=i, score=0.1))
            continue
        score = 0.0
        for kw in keywords:
            if kw and kw in text:
                score += 1.0 / max(1, len(keywords))
        scored.append(PageCandidate(page_index=i, score=round(score, 4)))

    scored.sort(key=lambda c: c.score, reverse=True)
    # 至少保留 top_k, 且不全部过滤掉 0 分页 (召回阶段宁可多).
    top = scored[:top_k]
    if not any(c.score > 0 for c in top):
        # 没有文本命中时退化为返回前 top_k 页.
        top = [PageCandidate(page_index=i, score=0.0) for i in range(min(top_k, len(pages)))]
    return top
