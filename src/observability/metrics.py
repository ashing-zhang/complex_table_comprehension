"""指标聚合: 统计题型分布、成功率、retry 次数等."""

from __future__ import annotations

import json
from collections import Counter, defaultdict
from threading import Lock
from typing import Any

from src.observability.logger import get_logger

logger = get_logger("metrics")


class MetricsCollector:
    """线程安全的指标聚合器."""

    def __init__(self) -> None:
        self._lock = Lock()
        self.total = 0
        self.success = 0
        self.failure = 0
        self.empty_answer = 0
        self.by_type: Counter[str] = Counter()
        self.by_type_success: Counter[str] = Counter()
        self.retry_counts: Counter[int] = Counter()
        self.errors: list[dict[str, Any]] = []

    def record(self, question_type: str, ok: bool, empty: bool, retries: int = 0, error: str | None = None, question_id: str = "") -> None:
        """记录一道题的执行结果."""
        with self._lock:
            self.total += 1
            self.by_type[question_type] += 1
            if ok:
                self.success += 1
                self.by_type_success[question_type] += 1
            else:
                self.failure += 1
            if empty:
                self.empty_answer += 1
            self.retry_counts[retries] += 1
            if error:
                self.errors.append({"id": question_id, "type": question_type, "error": error})

    def summary(self) -> dict[str, Any]:
        """返回可序列化的汇总字典."""
        with self._lock:
            return {
                "total": self.total,
                "success": self.success,
                "failure": self.failure,
                "empty_answer": self.empty_answer,
                "by_type": dict(self.by_type),
                "by_type_success": dict(self.by_type_success),
                "retry_counts": dict(self.retry_counts),
                "errors": self.errors[:200],
            }

    def log_summary(self) -> None:
        """将汇总信息输出到日志."""
        s = self.summary()
        logger.info("metrics: %s", json.dumps(s, ensure_ascii=False))


_metrics = MetricsCollector()


def get_metrics() -> MetricsCollector:
    """获取全局 MetricsCollector 单例."""
    return _metrics
