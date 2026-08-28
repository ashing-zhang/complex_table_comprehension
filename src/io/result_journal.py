"""单题结果日志 (JSONL): 每完成一道题立即追加一行, 用于溯源与恢复.

运行指南:
    - run 模式下由 Orchestrator 在每题完成后调用 append() 写入 (flush+fsync 落盘,
      Ctrl+C 中断不丢已完成结果); 每行是一条 TaskResult 的 JSON 对象.
    - 断点续跑: 重新运行 run 模式时, 日志中 ok=True 的题目自动跳过不再求解.
    - 恢复导出: RUN_MODE=recover python -m src.main 仅从日志生成 submission.xlsx,
      不调用模型.
    - 日志路径由 configs/*.yaml 的 data.journal 或环境变量 JOURNAL 指定.
"""

from __future__ import annotations

import json
import os
import threading
from dataclasses import asdict
from pathlib import Path

from src.observability.logger import get_logger
from src.table.models import TaskResult

logger = get_logger("result_journal")


class ResultJournal:
    """单题结果 JSONL 日志: append-only 追加写, 按 id 恢复时保留最后一次记录."""

    def __init__(self, journal_path: str | Path) -> None:
        """初始化日志路径 (文件可不存在, 首次 append 时自动创建)."""
        self.path = Path(journal_path)
        self._lock = threading.Lock()

    def load(self) -> dict[str, TaskResult]:
        """读取日志并按 id 去重 (同一 id 保留最后一次), 损坏行跳过并告警.

        Returns:
            id -> TaskResult 映射.
        """
        results: dict[str, TaskResult] = {}
        if not self.path.exists():
            return results
        bad_lines = 0
        with open(self.path, "r", encoding="utf-8") as f:
            for lineno, line in enumerate(f, 1):
                line = line.strip()
                if not line:
                    continue
                try:
                    record = json.loads(line)
                    result = TaskResult(
                        id=str(record.get("id", "")),
                        answer=str(record.get("answer") or ""),
                        confidence=record.get("confidence"),
                        evidence=list(record.get("evidence") or []),
                        warnings=[str(w) for w in (record.get("warnings") or [])],
                        ok=bool(record.get("ok", False)),
                        error_code=record.get("error_code"),
                        error_message=record.get("error_message"),
                        retries=int(record.get("retries", 0)),
                    )
                except (json.JSONDecodeError, TypeError, ValueError) as exc:
                    bad_lines += 1
                    logger.warning("journal line %d invalid, skipped: %s", lineno, exc)
                    continue
                results[result.id] = result
        if bad_lines:
            logger.warning("journal %s: %d bad line(s) skipped", self.path, bad_lines)
        logger.info("journal loaded: %d result(s) from %s", len(results), self.path)
        return results

    def append(self, result: TaskResult) -> None:
        """追加一条结果并立即刷盘; 写入失败仅告警, 不中断主流程."""
        record = asdict(result)
        try:
            with self._lock:
                self.path.parent.mkdir(parents=True, exist_ok=True)
                with open(self.path, "a", encoding="utf-8") as f:
                    f.write(json.dumps(record, ensure_ascii=False, default=str) + "\n")
                    f.flush()
                    os.fsync(f.fileno())
        except OSError as exc:
            logger.error("journal append failed for id=%s: %s", result.id, exc)
