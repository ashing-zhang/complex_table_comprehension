"""Runner / Orchestrator (TECHNICAL_SOLUTION.md 第 28, 38 章).

执行整批题目, 单题失败不影响其他题.
并发控制 (TECHNICAL_SOLUTION.md 第 48 章): 使用 Semaphore, 不直接 asyncio.gather.
"""

from __future__ import annotations

import json
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import TYPE_CHECKING

from src.config.settings import get_settings
from src.io.question_loader import LoadResult
from src.io.submission_writer import preflight_submission, write_submission
from src.observability.logger import get_logger
from src.observability.metrics import get_metrics
from src.observability.trace import TraceContext
from src.pipeline.task_pipeline import solve_question
from src.table.models import TaskResult

if TYPE_CHECKING:
    from src.vision.qwen_client import QwenClient

logger = get_logger("runner")


class Orchestrator:
    """整批执行编排器."""

    def __init__(
        self,
        tests_path: str | Path,
        files_dir: str | Path,
        output_path: str | Path,
        *,
        client: "QwenClient | None" = None,
        max_workers: int | None = None,
        save_intermediate: bool = True,
        dpi: int | None = None,
    ) -> None:
        """初始化 Orchestrator.

        Args:
            tests_path: tests.xlsx 路径.
            files_dir: 表格文件目录.
            output_path: submission.xlsx 输出路径.
            client: QwenClient (None 则在子线程内按需创建).
            max_workers: 最大并发.
            save_intermediate: 是否保存中间产物.
            dpi: PDF 渲染分辨率.
        """
        self.tests_path = Path(tests_path)
        self.files_dir = Path(files_dir)
        self.output_path = Path(output_path)
        self.client = client
        settings = get_settings()
        self.max_workers = max_workers or settings.concurrency.max_workers
        self.save_intermediate = save_intermediate
        self.dpi = dpi or settings.pipeline.pdf_dpi

    def run(self, load_result: LoadResult) -> Path:
        """执行整批题目并写出 submission.xlsx.

        Args:
            load_result: question_loader 返回的加载结果 (含 invalid 行).

        Returns:
            写出的 submission.xlsx 路径.
        """
        results: list[TaskResult] = []
        # 非法行 -> 空答案, 保证 id 完整性.
        for bad in load_result.invalid_rows:
            results.append(
                TaskResult(
                    id=str(bad.get("id", "")),
                    answer="",
                    ok=False,
                    error_code=str(bad.get("error", "")),
                    error_message=str(bad.get("message", "")),
                    warnings=[str(bad.get("message", ""))],
                )
            )

        questions = load_result.questions
        if not questions:
            logger.warning("no valid questions to solve")
            return self._finalize(results, load_result)

        # 并发执行 (TECHNICAL_SOLUTION.md 第 48 章: 使用 Semaphore 等价控制).
        workers = min(self.max_workers, len(questions))
        logger.info("running %d questions with %d workers", len(questions), workers)

        # 共享 client 避免每题新建 OpenAI 连接池.
        shared_client = self.client
        if shared_client is None:
            try:
                from src.vision.qwen_client import get_qwen_client

                shared_client = get_qwen_client()
            except Exception as exc:  # noqa: BLE001
                logger.warning("no API key configured, will produce empty answers: %s", exc)
                shared_client = None  # type: ignore[assignment]

        if shared_client is None:
            # 没有 API key: 直接生成空答案 (MVP 兜底, 仍保证 submission 合法).
            for q in questions:
                results.append(
                    TaskResult(
                        id=q.id,
                        answer="",
                        ok=False,
                        error_code="model_error",
                        error_message="no QwenClient available",
                        warnings=["no QwenClient available"],
                    )
                )
            return self._finalize(results, load_result)

        # 用闭包传递 shared_client.
        def _one(q):
            return solve_question(
                q,
                self.files_dir,
                client=shared_client,
                debug_dir=get_settings().resolve_path(get_settings().data.debug) / q.id,
                save_intermediate=self.save_intermediate,
                dpi=self.dpi,
            )

        with ThreadPoolExecutor(max_workers=workers) as pool:
            future_map = {pool.submit(_one, q): q for q in questions}
            for fut in as_completed(future_map):
                q = future_map[fut]
                try:
                    res = fut.result()
                except Exception as exc:  # noqa: BLE001
                    logger.exception("question %s crashed: %s", q.id, exc)
                    res = TaskResult(
                        id=q.id,
                        answer="",
                        ok=False,
                        error_code="model_error",
                        error_message=str(exc),
                        warnings=[str(exc)],
                    )
                results.append(res)
                logger.info("question %s done: ok=%s answer_len=%d", q.id, res.ok, len(res.answer or ""))

        return self._finalize(results, load_result)

    def _finalize(self, results: list[TaskResult], load_result: LoadResult) -> Path:
        """写出并 preflight 检查."""
        # 按 tests.xlsx 原始行序排序: invalid 行用 "order" 字段, 合法题目用 extra["_order"].
        order: dict[str, int] = {}
        for bad in load_result.invalid_rows:
            order[str(bad.get("id", ""))] = int(bad.get("order", 1 << 30))
        for q in load_result.questions:
            order[q.id] = int(q.extra.get("_order", 1 << 30))
        results.sort(key=lambda r: order.get(r.id, 1 << 30))

        out = write_submission(results, self.output_path)

        # preflight 检查.
        expected_ids = load_result.all_ids()
        ok, issues = preflight_submission(expected_ids, out)
        if not ok:
            logger.error("submission preflight FAILED: %s", issues)
        else:
            logger.info("submission preflight OK: %d rows", len(results))
        return out
