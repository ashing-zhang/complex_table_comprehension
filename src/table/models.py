"""核心数据模型: Canonical Table Representation (CTR).

按 TECHNICAL_SOLUTION.md 第 5 章定义:
- Cell: 单元格 (text/row/col/rowspan/colspan/bbox/confidence)
- Table: 行列/单元格/页索引
- Question: 题目
- TaskResult: 任务结果
- Page / Document: 文档与页面
- TableCandidate: 表格候选
- ErrorCode: 错误枚举

行列均使用 0-based 编号.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from enum import Enum
from typing import Any, Literal


class ErrorCode(Enum):
    """统一错误码 (TECHNICAL_SOLUTION.md 第 37 章)."""

    FILE_NOT_FOUND = "file_not_found"
    INVALID_EXCEL = "invalid_excel"
    PDF_PARSE_ERROR = "pdf_parse_error"
    IMAGE_ERROR = "image_error"
    PAGE_NOT_FOUND = "page_not_found"
    TABLE_NOT_FOUND = "table_not_found"
    MODEL_ERROR = "model_error"
    INVALID_JSON = "invalid_json"
    STRUCTURE_INVALID = "structure_invalid"
    VALUE_NOT_FOUND = "value_not_found"
    CALCULATION_ERROR = "calculation_error"
    FORMAT_ERROR = "format_error"


class TableAgentError(Exception):
    """表格 Agent 通用异常基类, 携带 ErrorCode."""

    def __init__(self, code: ErrorCode, message: str, *, question_id: str | None = None) -> None:
        super().__init__(message)
        self.code = code
        self.question_id = question_id


@dataclass
class Cell:
    """单元格.

    row/col 使用 0-based, rowspan/colspan >=1 表示真实合并覆盖范围.
    bbox 保存视觉位置 (x0, y0, x1, y1), confidence 保存识别置信度.
    """

    text: str
    row: int
    col: int
    rowspan: int = 1
    colspan: int = 1
    bbox: tuple[float, float, float, float] | None = None
    confidence: float | None = None

    def occupies(self, r: int, c: int) -> bool:
        """判断该单元格是否占用 (r, c) 位置."""
        return self.row <= r < self.row + self.rowspan and self.col <= c < self.col + self.colspan

    def to_dict(self) -> dict[str, Any]:
        """序列化为可 JSON 化的字典 (与 structure 答案格式对齐)."""
        return {
            "text": self.text,
            "row": self.row,
            "col": self.col,
            "rowspan": self.rowspan,
            "colspan": self.colspan,
        }


@dataclass
class Table:
    """逻辑表格 (Canonical Table Representation)."""

    row_count: int
    col_count: int
    cells: list[Cell] = field(default_factory=list)
    page_indices: list[int] = field(default_factory=list)
    bbox: tuple[float, float, float, float] | None = None
    title: str | None = None
    header_row_count: int = 1
    column_paths: list[list[str]] = field(default_factory=list)

    def to_structure_json(self) -> dict[str, Any]:
        """生成 structure 题型答案 JSON 结构."""
        return {
            "row_count": self.row_count,
            "col_count": self.col_count,
            "cells": [c.to_dict() for c in self.cells],
        }


@dataclass
class Question:
    """题目.

    id 统一保留为 str, 避免 Excel 类型自动转换造成不一致.
    """

    id: str
    file_name: str
    question_type: Literal["structure", "extract", "thinking"]
    question: str
    table_hint: str | None = None
    answer_format: str | None = None
    extra: dict[str, Any] = field(default_factory=dict)


@dataclass
class TaskResult:
    """单题执行结果."""

    id: str
    answer: str
    confidence: float | None = None
    evidence: list[dict[str, Any]] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    ok: bool = True
    error_code: str | None = None
    error_message: str | None = None
    retries: int = 0


@dataclass
class Page:
    """文档页面: 原始图像 + 预处理图像 + 元数据."""

    index: int
    image_path: str
    processed_image_path: str | None = None
    width: int = 0
    height: int = 0
    rotation_angle: int = 0
    text: str = ""
    regions: list["PageRegion"] = field(default_factory=list)


@dataclass
class PageRegion:
    """页面区域分类 (header/footer/table/footnote/body)."""

    type: str
    bbox: tuple[float, float, float, float]
    text: str = ""


@dataclass
class Document:
    """文档: 多个页面."""

    file_name: str
    pages: list[Page] = field(default_factory=list)


@dataclass
class TableCandidate:
    """表格候选 (页面 + bbox + 标题 + 预览 + 得分)."""

    page_index: int
    bbox: tuple[float, float, float, float]
    title: str | None = None
    text_preview: str = ""
    score: float = 0.0
