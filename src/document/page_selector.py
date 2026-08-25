"""页面定位 (TECHNICAL_SOLUTION.md 第 8 章).

召回阶段: 优先显式页码 -> LLM 关键词 -> 正则关键词 -> top-k pages.
宁可多召回, 不过早过滤.

运行指南:
    本模块由 src.pipeline.task_pipeline 调用, 不直接运行.
    通过 select_pages(document, question, client=...) 传入 QwenClient,
    缺省时使用全局单例 get_qwen_client().
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from src.config.settings import get_settings
from src.observability.logger import get_logger
from src.prompts.keyword_prompt import build_keyword_prompt
from src.table.models import ErrorCode, TableAgentError

if TYPE_CHECKING:
    from src.observability.trace import TraceContext
    from src.table.models import Document, Question
    from src.vision.qwen_client import QwenClient

logger = get_logger("page_selector")


@dataclass
class PageCandidate:
    """页面候选."""

    page_index: int
    score: float


@dataclass
class Keyword:
    """带权重与同义词的语义关键词."""

    text: str
    weight: float = 0.5
    aliases: list[str] = field(default_factory=list)

    def matches(self, page_text: str) -> bool:
        """判断该关键词 (含同义词) 是否在页面文本中出现."""
        if self.text and self.text in page_text:
            return True
        return any(a and a in page_text for a in self.aliases)


_PAGE_NUM_RE = re.compile(r"第\s*([0-9０-９]+)\s*页")
# 支持 "第3页到第4页" / "第3至4页" / "第3-4页".
_RANGE_RE = re.compile(r"第\s*([0-9０-９]+)\s*页?\s*(?:到|至|[-~])\s*第?\s*([0-9０-９]+)\s*页")

# 通用问句词, 不作为召回关键词.
_QUESTION_STOPWORDS = {
    "什么", "怎么", "如何", "请问", "提取", "计算", "恢复", "列出",
    "找出", "多少", "几个", "项数", "数量", "总计", "合计", "总和",
    "求和", "加总", "总额", "总金额", "总数", "总共", "排序",
    "从大到小", "从小到大", "降序", "升序", "最大", "最高", "最多",
    "最小", "最低", "最少", "比例", "占比", "比率", "比重",
    "增长率", "增速", "增幅", "增长", "同比", "环比",
}


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


def _llm_extract_keywords(
    question: "Question",
    *,
    client: "QwenClient | None" = None,
    trace: "TraceContext | None" = None,
) -> list[Keyword]:
    """通过 LLM 抽取带权重的语义关键词.

    Args:
        question: 题目.
        client: QwenClient; None 时使用全局单例.
        trace: 追踪上下文.

    Returns:
        Keyword 列表 (可能为空, 表示 LLM 调用失败或无可抽取实体).
    """
    if client is None:
        try:
            from src.vision.qwen_client import get_qwen_client

            client = get_qwen_client()
        except TableAgentError as exc:
            logger.warning("llm keyword skipped, client unavailable: %s", exc)
            return []
        except Exception as exc:  # noqa: BLE001
            logger.warning("llm keyword skipped, client init failed: %s", exc)
            return []

    system, user = build_keyword_prompt(question.question, table_hint=question.table_hint)
    messages: list[dict[str, object]] = [
        {"role": "system", "content": system},
        {"role": "user", "content": user},
    ]

    try:
        raw = client.chat(messages, trace=trace, stage="keyword_extract")
    except TableAgentError as exc:
        logger.warning("llm keyword call failed: %s", exc)
        return []
    except Exception as exc:  # noqa: BLE001
        logger.warning("llm keyword unexpected error: %s", exc)
        return []

    parsed = _parse_keyword_json(raw)
    if parsed is None:
        logger.warning("llm keyword invalid json, raw head: %r", raw[:200])
        return []

    keywords: list[Keyword] = []
    for item in parsed:
        if not isinstance(item, dict):
            continue
        text = item.get("text")
        if not isinstance(text, str) or not text.strip():
            continue
        weight = item.get("weight", 0.5)
        try:
            weight = float(weight)
        except (TypeError, ValueError):
            weight = 0.5
        weight = max(0.0, min(weight, 1.0))
        aliases_raw = item.get("aliases", [])
        aliases = [str(a).strip() for a in aliases_raw if isinstance(a, str) and a.strip()]
        keywords.append(Keyword(text=text.strip(), weight=weight, aliases=aliases))

    logger.info("llm keywords extracted: %d items for question %s", len(keywords), question.id)
    return keywords


def _parse_keyword_json(raw: str) -> list[dict[str, object]] | None:
    """从模型回复中解析关键词 JSON 数组.

    容错: 去除 markdown 代码块包裹, 定位首个 '[' 到匹配的 ']' 区间.
    """
    if not raw:
        return None
    text = raw.strip()
    if text.startswith("```"):
        # 去除 ```json 或 ``` 包裹.
        text = re.sub(r"^```[a-zA-Z]*\n?", "", text)
        text = re.sub(r"\n?```$", "", text).strip()

    if text.startswith("["):
        try:
            data = json.loads(text)
        except json.JSONDecodeError:
            return None
        return data if isinstance(data, list) else None

    # 在含说明性文字的回复中尝试定位首个数组.
    start = text.find("[")
    end = text.rfind("]")
    if start != -1 and end != -1 and end > start:
        try:
            data = json.loads(text[start : end + 1])
        except json.JSONDecodeError:
            return None
        return data if isinstance(data, list) else None
    return None


def _regex_extract_keywords(question: "Question") -> list[Keyword]:
    """基于正则抽取中文/英文/数字片段作为兜底关键词.

    过滤通用问句词, 权重统一 0.5 (中等).
    """
    keywords: list[Keyword] = []
    seen: set[str] = set()

    if question.table_hint:
        hint = question.table_hint.strip()
        if hint and hint not in seen:
            seen.add(hint)
            keywords.append(Keyword(text=hint, weight=1.0))

    text = question.question or ""
    # 中文连续片段 (>=2 字符).
    for m in re.finditer(r"[\u4e00-\u9fa5]{2,}", text):
        s = m.group(0)
        if s in _QUESTION_STOPWORDS or s in seen:
            continue
        seen.add(s)
        keywords.append(Keyword(text=s, weight=0.5))

    # 英文/数字 (>=2 字符, 如 2024 / Q3 / Apple).
    for m in re.finditer(r"[A-Za-z0-9]{2,}", text):
        s = m.group(0)
        if s in seen:
            continue
        seen.add(s)
        keywords.append(Keyword(text=s, weight=1.0))

    return keywords


def _merge_keywords(llm_kws: list[Keyword], regex_kws: list[Keyword]) -> list[Keyword]:
    """合并 LLM 与正则关键词, LLM 优先, 正则补充 LLM 未覆盖的项."""
    if not regex_kws:
        return llm_kws
    if not llm_kws:
        return regex_kws

    seen: set[str] = set()
    merged: list[Keyword] = []
    for kw in llm_kws:
        key = kw.text
        if key in seen:
            continue
        seen.add(key)
        merged.append(kw)
    for kw in regex_kws:
        if kw.text in seen:
            continue
        seen.add(kw.text)
        merged.append(kw)
    return merged


def _score_pages_by_keywords(
    pages: list,
    keywords: list[Keyword],
) -> list[PageCandidate]:
    """按关键词命中给每页打分, 归一化到 [0, 1]."""
    total_weight = sum(kw.weight for kw in keywords) or 1.0
    scored: list[PageCandidate] = []
    for i, page in enumerate(pages):
        text = page.text or ""
        if not text:
            scored.append(PageCandidate(page_index=i, score=0.0))
            continue
        score = 0.0
        for kw in keywords:
            if kw.matches(text):
                score += kw.weight / total_weight
        scored.append(PageCandidate(page_index=i, score=round(score, 4)))
    return scored


def select_pages(
    document: "Document",
    question: "Question",
    *,
    top_k: int = 5,
    client: "QwenClient | None" = None,
    trace: "TraceContext | None" = None,
    use_llm: bool | None = None,
) -> list[PageCandidate]:
    """选择候选页面.

    策略:
    1. 题目显式页码 -> 直接优先返回这些页 (按顺序), 补充相邻页.
    2. 否则: LLM 关键词 -> 正则关键词 -> 合并后按命中打分, 取 top_k.
       LLM 调用失败时退化到纯正则关键词召回.
    3. 单页文档直接返回该页.

    Args:
        document: 已加载的文档.
        question: 题目.
        top_k: 召回上限.
        client: QwenClient; None 时按需使用全局单例.
        trace: 追踪上下文.
        use_llm: 是否启用 LLM 关键词抽取; None 时读取 settings.pipeline.use_llm_keywords.

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

    # 关键词召回: LLM 优先, 正则兜底, 合并后打分.
    if use_llm is None:
        use_llm = get_settings().pipeline.use_llm_keywords

    llm_keywords: list[Keyword] = []
    if use_llm:
        llm_keywords = _llm_extract_keywords(question, client=client, trace=trace)

    regex_keywords = _regex_extract_keywords(question)
    keywords = _merge_keywords(llm_keywords, regex_keywords)

    if not keywords:
        # 无任何关键词 (例如纯结构题且无 table_hint): 退化为前 top_k 页.
        return [PageCandidate(page_index=i, score=0.0) for i in range(min(top_k, len(pages)))]

    scored = _score_pages_by_keywords(pages, keywords)
    scored.sort(key=lambda c: c.score, reverse=True)

    top = scored[:top_k]
    if not any(c.score > 0 for c in top):
        # 没有文本命中时退化为返回前 top_k 页 (召回阶段宁可多).
        top = [PageCandidate(page_index=i, score=0.0) for i in range(min(top_k, len(pages)))]
    return top
