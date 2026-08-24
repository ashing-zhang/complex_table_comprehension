"""提交文件写出与提交前检查 (TECHNICAL_SOLUTION.md 第 39-40 章).

写出 submission.xlsx 并在写出前自动执行 preflight 检查.
"""

from __future__ import annotations

import json
from dataclasses import asdict
from pathlib import Path
from typing import Any

import pandas as pd

from src.config.schemas import EMPTY_ANSWER, SUBMISSION_COLUMNS
from src.observability.logger import get_logger
from src.observability.metrics import get_metrics
from src.table.models import TaskResult

logger = get_logger("submission_writer")


def preflight_submission(
    expected_ids: list[str],
    submission_path: str | Path,
) -> tuple[bool, list[str]]:
    """提交前检查 (TECHNICAL_SOLUTION.md 第 40 章 8 步).

    Returns:
        (ok, issues): ok 表示是否通过, issues 为问题清单.
    """
    submission_path = Path(submission_path)
    issues: list[str] = []
    if not submission_path.exists():
        return False, [f"submission file not found: {submission_path}"]

    try:
        df = pd.read_excel(submission_path)
    except Exception as exc:  # noqa: BLE001
        return False, [f"cannot read submission: {exc}"]

    # [2] 行数检查.
    if len(df) != len(expected_ids):
        issues.append(f"row count mismatch: submission={len(df)} expected={len(expected_ids)}")

    # [1,3] id 列存在 + id 集合相等.
    if "id" not in df.columns:
        return False, ["submission missing 'id' column"]
    if "answer" not in df.columns:
        issues.append("submission missing 'answer' column")

    sub_ids_raw = df["id"].tolist()
    sub_ids = [_to_str_id(x) for x in sub_ids_raw]
    expected_set = set(expected_ids)
    sub_set = set(sub_ids)

    if expected_set != sub_set:
        missing = expected_set - sub_set
        extra = sub_set - expected_set
        if missing:
            issues.append(f"missing ids: {sorted(missing)[:10]}")
        if extra:
            issues.append(f"extra ids: {sorted(extra)[:10]}")

    # [4] 重复 id 检查.
    seen: set[str] = set()
    dupes: list[str] = []
    for sid in sub_ids:
        if sid in seen:
            dupes.append(sid)
        seen.add(sid)
    if dupes:
        issues.append(f"duplicate ids: {sorted(set(dupes))[:10]}")

    # [5] 空答案统计.
    if "answer" in df.columns:
        empty_n = int(df["answer"].astype(str).str.strip().isin(["", "nan"]).sum())
        if empty_n:
            logger.info("preflight: %d empty answers", empty_n)

    # [6,7] structure / json 答案合法性 (按 answer_format 不可知, 这里只做基础 JSON 校验).
    if "answer" in df.columns:
        for sid, ans in zip(sub_ids, df["answer"].tolist()):
            ans_str = "" if ans is None else str(ans)
            if ans_str.strip().startswith("{") or ans_str.strip().startswith("["):
                try:
                    json.loads(ans_str)
                except Exception as exc:  # noqa: BLE001
                    issues.append(f"id={sid} invalid JSON answer: {exc}")

    # [8] Excel 可读性已通过 (前面 read_excel 成功).
    return (len(issues) == 0), issues


def write_submission(results: list[TaskResult], output_path: str | Path) -> Path:
    """写出 submission.xlsx, 每道题一行.

    Args:
        results: 所有题目结果 (含失败/空答案).
        output_path: 输出 xlsx 路径.

    Returns:
        写出的文件路径.
    """
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    rows = []
    for r in results:
        answer = r.answer if r.answer is not None else EMPTY_ANSWER
        rows.append({"id": r.id, "answer": answer})

    df = pd.DataFrame(rows, columns=SUBMISSION_COLUMNS)
    # 确保 id 为字符串类型, 防止 Excel 自动转数字.
    df["id"] = df["id"].astype(str)
    df["answer"] = df["answer"].astype(str)

    df.to_excel(output_path, index=False)
    logger.info("wrote submission: %s (%d rows)", output_path, len(df))
    get_metrics().log_summary()
    return output_path


def _to_str_id(raw: Any) -> str:
    """将 raw id 强制转为 str."""
    if raw is None:
        return ""
    if isinstance(raw, float) and raw.is_integer():
        return str(int(raw))
    if isinstance(raw, int):
        return str(raw)
    return str(raw).strip()
