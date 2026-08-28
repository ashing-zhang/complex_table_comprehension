"""从 data/debug/<id>/final_answer.json 恢复答案.

运行指南:
    - 不直接运行; 由 RUN_MODE=recover_debug python -m src.main 调用.
    - 扫描 debug 目录下所有纯数字命名的子目录, 读取 final_answer.json.
    - 返回 id -> TaskResult 映射, 供 Orchestrator.recover_debug 复用.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

from src.observability.logger import get_logger
from src.table.models import TaskResult

logger = get_logger("debug_recovery")

_NUMERIC_RE = re.compile(r"^\d+$")


def load_debug_answers(debug_dir: str | Path) -> dict[str, TaskResult]:
    """扫描 debug 目录, 从各数字子目录的 final_answer.json 恢复答案.

    Args:
        debug_dir: data/debug 目录路径.

    Returns:
        id -> TaskResult 映射; 缺失/损坏的条目跳过并告警.
    """
    debug_dir = Path(debug_dir)
    results: dict[str, TaskResult] = {}
    if not debug_dir.is_dir():
        logger.warning("debug dir not found: %s", debug_dir)
        return results

    for child in sorted(debug_dir.iterdir()):
        if not child.is_dir() or not _NUMERIC_RE.match(child.name):
            continue
        fa_path = child / "final_answer.json"
        if not fa_path.exists():
            logger.warning("skip id=%s: final_answer.json missing", child.name)
            continue
        try:
            data = json.loads(fa_path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError) as exc:
            logger.warning("skip id=%s: cannot read final_answer.json: %s", child.name, exc)
            continue

        qid = str(data.get("id") or child.name)
        answer = data.get("answer")
        results[qid] = TaskResult(
            id=qid,
            answer=str(answer) if answer is not None else "",
            confidence=data.get("confidence"),
            evidence=list(data.get("evidence") or []),
            warnings=[str(w) for w in (data.get("warnings") or [])],
            ok=bool(data.get("ok", False)),
            error_code=data.get("error_code"),
            error_message=data.get("error_message"),
            retries=int(data.get("retries", 0)),
        )

    logger.info("debug recovery: %d result(s) from %s", len(results), debug_dir)
    return results
