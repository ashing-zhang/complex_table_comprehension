"""追踪上下文: 为单道题记录可追溯链路.

按 SPEC/TECHNICAL_SOLUTION 的要求, 每道题需要能回答:
"用了哪个文件? 定位到哪一页? 选择了哪个表格? Qwen 输出了什么? 最终答案?"
"""

from __future__ import annotations

import json
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from src.observability.logger import get_logger

logger = get_logger("trace")


@dataclass
class TraceContext:
    """单题执行追踪上下文.

    各阶段产出可挂载到 events 字段, 最终序列化到 data/debug/<id>/trace.json.
    """

    question_id: str
    file_name: str = ""
    question_type: str = ""
    events: list[dict[str, Any]] = field(default_factory=list)
    model_calls: list[dict[str, Any]] = field(default_factory=list)
    started_at: float = field(default_factory=time.time)
    finished_at: float | None = None

    def event(self, name: str, **payload: Any) -> None:
        """记录一个阶段事件."""
        self.events.append({"name": name, "ts": time.time(), "payload": payload})
        logger.info("[%s] %s %s", self.question_id, name, json.dumps(payload, ensure_ascii=False)[:400])

    def model_call(self, model: str, stage: str, latency: float, tokens: int = 0, **meta: Any) -> None:
        """记录一次模型调用."""
        self.model_calls.append(
            {"model": model, "stage": stage, "latency": latency, "tokens": tokens, **meta}
        )

    def finalize(self, debug_dir: Path) -> None:
        """将追踪信息序列化到 debug 目录."""
        self.finished_at = time.time()
        try:
            debug_dir.mkdir(parents=True, exist_ok=True)
            out = {
                "question_id": self.question_id,
                "file_name": self.file_name,
                "question_type": self.question_type,
                "started_at": self.started_at,
                "finished_at": self.finished_at,
                "duration_sec": (self.finished_at or self.started_at) - self.started_at,
                "events": self.events,
                "model_calls": self.model_calls,
            }
            with open(debug_dir / "trace.json", "w", encoding="utf-8") as f:
                json.dump(out, f, ensure_ascii=False, indent=2)
        except Exception as exc:  # noqa: BLE001
            logger.warning("trace finalize failed for %s: %s", self.question_id, exc)


def trace_event(trace: TraceContext, name: str, **payload: Any) -> None:
    """便捷封装: 记录事件 (允许 trace 为 None)."""
    if trace is None:
        return
    trace.event(name, **payload)
