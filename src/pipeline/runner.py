"""Runner / Orchestrator (TECHNICAL_SOLUTION.md 第 28, 38 章).

执行整批题目, 单题失败不影响其他题.
并发控制 (TECHNICAL_SOLUTION.md 第 48 章): 使用 Semaphore, 不直接 asyncio.gather.
健壮性: 每题完成后立即追加到 JSONL 结果日志 (断点续跑 + 恢复导出), Ctrl+C 中断不丢已完成结果.
"""

from __future__ import annotations

from concurrent.futures import Future, ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import TYPE_CHECKING, Any

from src.config.settings import get_settings
from src.io.question_loader import LoadResult
from src.io.result_journal import ResultJournal
from src.io.submission_writer import preflight_submission, write_submission
from src.observability.logger import get_logger
from src.observability.metrics import get_metrics
from src.observability.trace import TraceContext
from src.pipeline.task_pipeline import solve_question
from src.table.models import Question, TaskResult

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
        journal_path: str | Path | None = None,
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
            journal_path: 单题结果 JSONL 日志路径 (None 则取配置 data.journal).
        """
        self.tests_path = Path(tests_path)
        self.files_dir = Path(files_dir)
        self.output_path = Path(output_path)
        self.client = client
        settings = get_settings()
        self.max_workers = max_workers or settings.concurrency.max_workers
        self.save_intermediate = save_intermediate
        self.dpi = dpi or settings.pipeline.pdf_dpi
        self.journal = ResultJournal(
            journal_path
            if journal_path is not None
            else settings.resolve_path(settings.data.journal)
        )

    def run(self, load_result: LoadResult) -> Path:
        """执行整批题目并写出 submission.xlsx.

        每题完成后立即追加写入 JSONL 结果日志; 重跑时日志中 ok=True 的题目
        自动跳过 (断点续跑), Ctrl+C 中断时在途结果会被收割后落盘.

        Args:
            load_result: question_loader 返回的加载结果 (含 invalid 行).

        Returns:
            写出的 submission.xlsx 路径.
        """
        results: list[TaskResult] = []
        # 非法行 -> 空答案, 保证 id 完整性.
        for bad in load_result.invalid_rows:
            results.append(self._invalid_row_result(bad))

        questions = load_result.questions
        if not questions:
            logger.warning("no valid questions to solve")
            return self._finalize(results, load_result)

        # 断点续跑: 日志中 ok=True 的题目直接复用, 其余进入待求解队列.
        stored = self.journal.load()
        reused = [r for q in questions if (r := stored.get(q.id)) is not None and r.ok]
        results.extend(reused)
        pending = [q for q in questions if not (stored.get(q.id) and stored[q.id].ok)]
        logger.info("resume check: %d done in journal, %d to solve", len(reused), len(pending))
        if not pending:
            return self._finalize(results, load_result)

        # 并发执行 (TECHNICAL_SOLUTION.md 第 48 章: 使用 Semaphore 等价控制).
        workers = min(self.max_workers, len(pending))
        logger.info("running %d questions with %d workers", len(pending), workers)

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
            for q in pending:
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
        def _one(q: Question) -> TaskResult:
            return solve_question(
                q,
                self.files_dir,
                client=shared_client,
                debug_dir=get_settings().resolve_path(get_settings().data.debug) / q.id,
                save_intermediate=self.save_intermediate,
                dpi=self.dpi,
            )

        processed: set[Future[TaskResult]] = set()
        future_map: dict[Future[TaskResult], Question] = {}
        pool = ThreadPoolExecutor(max_workers=workers)
        try:
            future_map = {pool.submit(_one, q): q for q in pending}
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
                processed.add(fut)
                results.append(res)
                # 单题完成即落盘 (flush+fsync), 中断不丢已完成结果.
                self.journal.append(res)
                logger.info("question %s done: ok=%s answer_len=%d", q.id, res.ok, len(res.answer or ""))
        except KeyboardInterrupt:
            self._handle_interrupt(pool, future_map, processed, results)
            raise
        else:
            pool.shutdown(wait=True)

        return self._finalize(results, load_result)

    def recover(self, load_result: LoadResult) -> Path:
        """仅从结果日志恢复已完成答案并写出 submission.xlsx (不调用模型).

        日志中缺失的题目以空答案占位, 保证行数与 id 完整; 缺失清单会告警提示.

        Args:
            load_result: question_loader 返回的加载结果 (含 invalid 行).

        Returns:
            写出的 submission.xlsx 路径.
        """
        stored = self.journal.load()
        results: list[TaskResult] = []
        for bad in load_result.invalid_rows:
            results.append(self._invalid_row_result(bad))

        missing: list[str] = []
        for q in load_result.questions:
            if (res := stored.get(q.id)) is not None:
                results.append(res)
            else:
                missing.append(q.id)
                results.append(
                    TaskResult(
                        id=q.id,
                        answer="",
                        ok=False,
                        error_code="not_recovered",
                        error_message="missing in result journal",
                        warnings=["missing in result journal"],
                    )
                )
        logger.info(
            "recover: %d/%d question(s) restored from journal %s",
            len(load_result.questions) - len(missing),
            len(load_result.questions),
            self.journal.path,
        )
        if missing:
            logger.warning(
                "recover: %d question(s) missing in journal (filled empty), sample: %s",
                len(missing),
                missing[:10],
            )
        return self._finalize(results, load_result)

    def _handle_interrupt(
        self,
        pool: ThreadPoolExecutor,
        future_map: dict[Future[TaskResult], Question],
        processed: set[Future[TaskResult]],
        results: list[TaskResult],
    ) -> None:
        """Ctrl+C 中断处理: 取消排队任务, 等待在途任务完成后收割进日志.

        Args:
            pool: 线程池.
            future_map: future -> question 映射.
            processed: 主循环已消费并写日志的 future 集合.
            results: 结果累积列表 (扫尾结果会追加进去).
        """
        logger.warning(
            "KeyboardInterrupt: cancelling queued questions, draining in-flight ones "
            "(press Ctrl+C again to force quit)...",
        )
        try:
            pool.shutdown(wait=True, cancel_futures=True)
        except KeyboardInterrupt:
            logger.error("forced exit; some in-flight results may be missing from journal")

        # 收割已完成但未被主循环消费的结果, 补写日志避免丢失.
        swept = 0
        for fut, q in future_map.items():
            if fut in processed or fut.cancelled() or not fut.done():
                continue
            try:
                res = fut.result()
            except Exception as exc:  # noqa: BLE001
                logger.warning("question %s failed during interrupt sweep: %s", q.id, exc)
                continue
            results.append(res)
            self.journal.append(res)
            swept += 1
        logger.warning(
            "interrupted: %d extra result(s) swept into journal %s; "
            "re-run to resume, or RUN_MODE=recover python -m src.main to export journaled results to xlsx",
            swept,
            self.journal.path,
        )

    @staticmethod
    def _invalid_row_result(bad: dict[str, Any]) -> TaskResult:
        """将 loader 的非法行转换为空答案 TaskResult, 保证 id 完整性."""
        return TaskResult(
            id=str(bad.get("id", "")),
            answer="",
            ok=False,
            error_code=str(bad.get("error", "")),
            error_message=str(bad.get("message", "")),
            warnings=[str(bad.get("message", ""))],
        )

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
