"""题目清单加载器 (TECHNICAL_SOLUTION.md 第 6 章).

读取 tests.xlsx, 校验必填字段 / question_type / id 唯一性 / file_name 存在性.
对非法题目记录 error 而不中断整个程序.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import pandas as pd

from src.config.schemas import (
    EMPTY_ANSWER,
    QUESTION_OPTIONAL_COLUMNS,
    QUESTION_REQUIRED_COLUMNS,
    VALID_ANSWER_FORMATS,
    VALID_QUESTION_TYPES,
)
from src.observability.logger import get_logger
from src.table.models import ErrorCode, Question, TableAgentError

logger = get_logger("question_loader")


_LEADING_ZERO_RE = re.compile(r"^\d+")


def resolve_file_name(file_name: str, files_dir: Path | None) -> tuple[str, bool]:
    """解析文件名, 容忍 tests.xlsx 中前导零不一致的情况.

    例: tests.xlsx 写 "58.pdf" / "0060.pdf", 实际文件为 "058.pdf" / "060.pdf".

    Returns:
        (resolved_name, found): resolved_name 为最终使用的文件名,
        found 表示 files_dir 中是否存在该文件.
    """
    if files_dir is None:
        return file_name, True
    if (files_dir / file_name).exists():
        return file_name, True
    m = _LEADING_ZERO_RE.match(file_name)
    if m:
        n = int(m.group(0))
        for width in (3, 2, 4, 1):
            cand = _LEADING_ZERO_RE.sub(str(n).zfill(width), file_name, count=1)
            if (files_dir / cand).exists():
                return cand, True
    return file_name, False


@dataclass
class LoadResult:
    """题目加载结果: 合法题目 + 非法行 (用于生成空答案)."""

    questions: list[Question] = field(default_factory=list)
    invalid_rows: list[dict[str, Any]] = field(default_factory=list)

    def all_ids(self) -> list[str]:
        """返回所有题目 id (含非法行), 用于 submission 行数完整性检查."""
        ids = [q.id for q in self.questions]
        ids.extend(row["id"] for row in self.invalid_rows if "id" in row)
        return ids


def _to_str_id(raw: Any) -> str:
    """将 raw id 强制转为 str, 避免 Excel 自动类型转换."""
    if raw is None:
        return ""
    if isinstance(raw, float) and raw.is_integer():
        return str(int(raw))
    if isinstance(raw, int):
        return str(raw)
    return str(raw).strip()


def load_questions(tests_path: str | Path, files_dir: str | Path | None = None) -> LoadResult:
    """读取 tests.xlsx 并校验.

    Args:
        tests_path: tests.xlsx 路径.
        files_dir: 表格文件目录, 用于校验 file_name 是否存在.

    Returns:
        LoadResult: 合法题目 + 非法行清单.
    """
    tests_path = Path(tests_path)
    if not tests_path.exists():
        raise TableAgentError(ErrorCode.INVALID_EXCEL, f"tests.xlsx not found: {tests_path}")

    try:
        df = pd.read_excel(tests_path, dtype={"id": object})
    except Exception as exc:  # noqa: BLE001
        raise TableAgentError(ErrorCode.INVALID_EXCEL, f"failed to read tests.xlsx: {exc}") from exc

    # 列名校验.
    missing = [c for c in QUESTION_REQUIRED_COLUMNS if c not in df.columns]
    if missing:
        raise TableAgentError(ErrorCode.INVALID_EXCEL, f"tests.xlsx missing required columns: {missing}")

    files_dir = Path(files_dir) if files_dir else None
    result = LoadResult()
    seen_ids: set[str] = set()
    seq = 0  # 全局顺序计数器, 保留 tests.xlsx 原始行序.

    for idx, row in df.iterrows():
        raw_id = row.get("id")
        qid = _to_str_id(raw_id)
        row_dict: dict[str, Any] = {"row_index": idx, "order": seq, "id": qid}
        seq += 1

        # id 唯一性.
        if not qid:
            row_dict["error"] = ErrorCode.INVALID_EXCEL.value
            row_dict["message"] = "empty id"
            result.invalid_rows.append(row_dict)
            continue
        if qid in seen_ids:
            row_dict["error"] = ErrorCode.INVALID_EXCEL.value
            row_dict["message"] = f"duplicate id: {qid}"
            result.invalid_rows.append(row_dict)
            continue
        seen_ids.add(qid)

        file_name = str(row.get("file_name") or "").strip()
        qtype = str(row.get("question_type") or "").strip()
        question_text = str(row.get("question") or "").strip()
        table_hint = row.get("table_hint")
        answer_format = row.get("answer_format")

        # question_type 校验: 非法时仍保留 id, 转为 invalid 行.
        if qtype not in VALID_QUESTION_TYPES:
            row_dict["error"] = ErrorCode.INVALID_EXCEL.value
            row_dict["message"] = f"invalid question_type: {qtype!r}"
            result.invalid_rows.append(row_dict)
            logger.warning("row %s id=%s invalid question_type=%r", idx, qid, qtype)
            continue

        if not file_name or not question_text:
            row_dict["error"] = ErrorCode.INVALID_EXCEL.value
            row_dict["message"] = "missing file_name or question"
            result.invalid_rows.append(row_dict)
            continue

        # answer_format 校验 (None 允许).
        fmt = str(answer_format).strip() if answer_format is not None and str(answer_format).lower() != "nan" else None
        if fmt is not None and fmt not in VALID_ANSWER_FORMATS:
            logger.warning("row %s id=%s unknown answer_format=%r, ignoring", idx, qid, fmt)
            fmt = None

        # file_name 存在性: 容忍前导零不一致, 找不到则标记 invalid.
        resolved_name, found = resolve_file_name(file_name, files_dir)
        if not found:
            row_dict["error"] = ErrorCode.FILE_NOT_FOUND.value
            row_dict["message"] = f"file not found: {file_name}"
            result.invalid_rows.append(row_dict)
            logger.warning("row %s id=%s file not found: %s", idx, qid, file_name)
            continue
        # 用解析后的文件名覆盖 (供 document_loader 直接使用).
        file_name = resolved_name

        # 处理 table_hint/answer 的 NaN -> None.
        hint = table_hint if (table_hint is not None and str(table_hint).lower() != "nan" and str(table_hint).strip()) else None
        hint = str(hint).strip() if hint is not None else None

        # 收集额外列 (例如可能存在的 answer 列等).
        extra = {
            k: v
            for k, v in row.to_dict().items()
            if k not in QUESTION_REQUIRED_COLUMNS + QUESTION_OPTIONAL_COLUMNS and v is not None
        }
        # 保留原始行序供 submission 排序.
        extra["_order"] = seq - 1

        question = Question(
            id=qid,
            file_name=file_name,
            question_type=qtype,  # type: ignore[arg-type]
            question=question_text,
            table_hint=hint,
            answer_format=fmt,
            extra=extra,
        )
        result.questions.append(question)

    logger.info(
        "loaded %d questions (%d invalid) from %s",
        len(result.questions),
        len(result.invalid_rows),
        tests_path,
    )
    return result
