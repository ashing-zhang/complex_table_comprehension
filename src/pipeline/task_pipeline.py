"""单题流水线 (TECHNICAL_SOLUTION.md 第 28 章 Orchestrator).

执行: document -> pages -> tables -> canonical table -> solver -> validator.
单题失败不影响其他题, 失败时 answer 填空.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import TYPE_CHECKING

from src.config.settings import get_settings
from src.document.image_preprocessor import preprocess_page
from src.document.page_selector import select_pages
from src.document.table_detector import detect_tables
from src.io.document_loader import load_document
from src.observability.logger import get_logger
from src.observability.metrics import get_metrics
from src.observability.trace import TraceContext
from src.table.models import ErrorCode, Question, Table, TableAgentError, TaskResult
from src.task.base import SolverContext
from src.task.extract import ExtractSolver
from src.task.structure import StructureSolver
from src.task.thinking import ThinkingSolver
from src.validation.answer_validator import validate_answer

if TYPE_CHECKING:
    from src.vision.qwen_client import QwenClient

logger = get_logger("task_pipeline")


def solve_question(
    question: Question,
    files_dir: str | Path,
    *,
    client: "QwenClient | None" = None,
    debug_dir: str | Path | None = None,
    save_intermediate: bool = True,
    dpi: int = 200,
) -> TaskResult:
    """执行单题完整流水线.

    Args:
        question: 题目.
        files_dir: 表格文件目录.
        client: QwenClient (None 则按需创建).
        debug_dir: 单题 debug 目录.
        save_intermediate: 是否保存中间产物.
        dpi: PDF 渲染分辨率.

    Returns:
        TaskResult (失败时 answer 为空字符串).
    """
    settings = get_settings()
    debug_dir = Path(debug_dir) if debug_dir else settings.resolve_path(settings.data.debug) / question.id
    trace = TraceContext(question_id=question.id, file_name=question.file_name, question_type=question.question_type)

    try:
        trace.event("start", question=question.question[:200])

        # 1. 文档加载.
        file_path = Path(files_dir) / question.file_name
        trace.event("load_document", file=question.file_name)
        document = load_document(file_path, dpi=dpi)
        trace.event("document_loaded", pages=len(document.pages))

        # 2. 页面定位 (召回): 显式页码 -> LLM/正则关键词 -> top-k.
        page_candidates = select_pages(
            document,
            question,
            top_k=settings.pipeline.page_top_k,
            client=client,
            trace=trace,
            use_llm=settings.pipeline.use_llm_keywords,
        )
        trace.event("page_selected", candidates=[(c.page_index, c.score) for c in page_candidates])
        if not page_candidates:
            raise TableAgentError(ErrorCode.PAGE_NOT_FOUND, "no candidate pages")

        # 3. 预处理页面 + 表格候选检测.
        proc_dir = debug_dir / "pages" if save_intermediate else None
        image_paths: list[str] = []
        for pc in page_candidates:
            page = document.pages[pc.page_index]
            if save_intermediate and proc_dir is not None:
                try:
                    preprocess_page(page, proc_dir, max_long_side=settings.pipeline.max_image_long_side)
                except TableAgentError:
                    pass
            # 优先用预处理图像 (若生成成功), 否则用原图.
            img = page.processed_image_path or page.image_path
            image_paths.append(img)

        tables = detect_tables(document, question, page_candidates, top_k=settings.pipeline.table_top_k)
        trace.event("tables_detected", count=len(tables))
        if not tables:
            raise TableAgentError(ErrorCode.TABLE_NOT_FOUND, "no candidate tables")

        # 4. 构造 SolverContext.
        candidate = tables[0]
        ctx = SolverContext(
            question=question,
            image_paths=image_paths,
            candidate=candidate,
            client=client,
            trace=trace,
            answer_format=question.answer_format,
        )

        # 5. 按 question_type 分发.
        canonical_table: Table | None = None
        result: TaskResult
        if question.question_type == "structure":
            solver = StructureSolver(client=client)
            result = solver.solve(ctx, table=canonical_table)
        elif question.question_type == "extract":
            solver = ExtractSolver(client=client)
            result = solver.solve(ctx, table=canonical_table)
        elif question.question_type == "thinking":
            solver = ThinkingSolver(client=client)
            result = solver.solve(ctx, table=canonical_table)
        else:
            raise TableAgentError(ErrorCode.INVALID_EXCEL, f"unknown question_type: {question.question_type}")

        # 6. 答案校验.
        result = validate_answer(question, result, canonical_table)

        # 7. 保存中间产物.
        if save_intermediate:
            _save_debug(debug_dir, question, result, tables, trace)

        # 8. 记录指标.
        empty = not (result.answer or "").strip()
        get_metrics().record(
            question_type=question.question_type,
            ok=result.ok,
            empty=empty,
            retries=0,
            error=None if result.ok else result.error_code,
            question_id=question.id,
        )

        trace.event("finish", ok=result.ok, empty=empty)
        return result

    except TableAgentError as exc:
        logger.warning("question %s failed: %s (%s)", question.id, exc, exc.code.value)
        get_metrics().record(
            question_type=question.question_type,
            ok=False,
            empty=True,
            retries=0,
            error=str(exc),
            question_id=question.id,
        )
        return TaskResult(
            id=question.id,
            answer="",
            ok=False,
            error_code=exc.code.value,
            error_message=str(exc),
            warnings=[str(exc)],
        )
    except Exception as exc:  # noqa: BLE001
        # 未知异常: 不影响其他题, 答案置空.
        logger.exception("question %s unexpected error: %s", question.id, exc)
        get_metrics().record(
            question_type=question.question_type,
            ok=False,
            empty=True,
            retries=0,
            error=f"unexpected: {exc}",
            question_id=question.id,
        )
        return TaskResult(
            id=question.id,
            answer="",
            ok=False,
            error_code=ErrorCode.MODEL_ERROR.value,
            error_message=str(exc),
            warnings=[f"unexpected: {exc}"],
        )
    finally:
        trace.finalize(Path(debug_dir) if debug_dir else Path("."))


def _save_debug(debug_dir: Path, question: Question, result: TaskResult, tables, trace: TraceContext) -> None:
    """保存单题 debug 产物."""
    try:
        debug_dir.mkdir(parents=True, exist_ok=True)
        with open(debug_dir / "question.json", "w", encoding="utf-8") as f:
            json.dump(
                {
                    "id": question.id,
                    "file_name": question.file_name,
                    "question_type": question.question_type,
                    "question": question.question,
                    "table_hint": question.table_hint,
                    "answer_format": question.answer_format,
                },
                f,
                ensure_ascii=False,
                indent=2,
            )
        with open(debug_dir / "table_candidates.json", "w", encoding="utf-8") as f:
            json.dump(
                [{"page_index": t.page_index, "score": t.score, "title": t.title, "preview": t.text_preview} for t in tables],
                f,
                ensure_ascii=False,
                indent=2,
            )
        with open(debug_dir / "final_answer.json", "w", encoding="utf-8") as f:
            json.dump(
                {
                    "id": result.id,
                    "answer": result.answer,
                    "ok": result.ok,
                    "confidence": result.confidence,
                    "warnings": result.warnings,
                    "error_code": result.error_code,
                    "evidence": result.evidence[:20],
                },
                f,
                ensure_ascii=False,
                indent=2,
            )
    except Exception as exc:  # noqa: BLE001
        logger.debug("save debug failed for %s: %s", question.id, exc)
