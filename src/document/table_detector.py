"""表格候选检测 (TECHNICAL_SOLUTION.md 第 9 章).

复杂表格的核心问题不是"有没有表格", 而是"题目需要回答的表格是哪一个".
本模块负责: 检测候选 -> 与题目匹配 -> 选出目标表格.

MVP 实现: 不依赖外部版面分析, 而是依赖后续视觉模型直接理解整页.
这里给出候选 + 评分框架, 默认将候选页视为单一候选表格.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from src.observability.logger import get_logger
from src.table.models import TableCandidate

if TYPE_CHECKING:
    from src.document.page_selector import PageCandidate
    from src.table.models import Document, Question

logger = get_logger("table_detector")


def detect_tables(
    document: "Document",
    question: "Question",
    page_candidates: list["PageCandidate"],
    *,
    top_k: int = 3,
) -> list[TableCandidate]:
    """检测表格候选.

    MVP: 将每个候选页视为一个"整页候选表格", 评分基于页面候选得分 +
    table_hint 在页面文本中的命中. 真正的表格区域定位交由视觉模型完成.

    Args:
        document: 文档.
        question: 题目.
        page_candidates: 页面候选.
        top_k: 保留前 k 个表格候选.

    Returns:
        TableCandidate 列表 (按 score 降序).
    """
    candidates: list[TableCandidate] = []
    pages = document.pages
    hint = (question.table_hint or "").strip()

    for pc in page_candidates:
        if pc.page_index < 0 or pc.page_index >= len(pages):
            continue
        page = pages[pc.page_index]
        text_preview = (page.text or "")[:200].replace("\n", " ")
        score = pc.score
        if hint and hint in (page.text or ""):
            score += 0.3
        candidates.append(
            TableCandidate(
                page_index=pc.page_index,
                bbox=(0.0, 0.0, float(page.width or 0), float(page.height or 0)),
                title=hint or None,
                text_preview=text_preview,
                score=round(score, 4),
            )
        )

    candidates.sort(key=lambda c: c.score, reverse=True)
    return candidates[:top_k]
