"""语义定位器 (TECHNICAL_SOLUTION.md 第 13 章).

在 Canonical Table 中根据问题关键词定位目标行/列/单元格.
不依赖 LLM, 基于文本相似度 + 路径匹配.
"""

from __future__ import annotations

from decimal import Decimal
from typing import TYPE_CHECKING

from src.observability.logger import get_logger
from src.reasoning.question_parser import QuestionIntent
from src.table.grid import build_grid, cell_at
from src.table.merge_resolver import find_cell_at
from src.table.normalizer import to_decimal

if TYPE_CHECKING:
    from src.table.models import Table

logger = get_logger("semantic_locator")


class SemanticLocator:
    """在 Table 中定位目标行/列/单元格."""

    def __init__(self, table: Table) -> None:
        """初始化定位器, 构建 grid 与列路径."""
        self.table = table
        try:
            self.grid = build_grid(table)
        except Exception:  # noqa: BLE001
            self.grid = None
        # 懒加载表头路径.
        if not table.column_paths:
            try:
                from src.table.header_resolver import resolve_column_paths

                resolve_column_paths(table)
            except Exception:  # noqa: BLE001
                pass

    def locate_row(self, keyword: str) -> int | None:
        """根据关键词定位行索引 (匹配首列或任意单元格文本)."""
        if not keyword:
            return None
        # 优先匹配第一列.
        for r in range(self.table.row_count):
            cell = self._cell(r, 0)
            if cell and keyword in cell.text:
                return r
        # 退化: 任意单元格匹配.
        for r in range(self.table.row_count):
            for c in range(self.table.col_count):
                cell = self._cell(r, c)
                if cell and keyword in cell.text:
                    return r
        return None

    def locate_column(self, keyword: str) -> int | None:
        """根据关键词定位列索引 (匹配表头路径或首行文本)."""
        if not keyword:
            return None
        # 优先匹配列路径 (多级表头).
        for c, path in enumerate(self.table.column_paths or []):
            joined = " ".join(path)
            if keyword in joined or any(keyword in seg for seg in path):
                return c
        # 退化: 首行表头匹配.
        for c in range(self.table.col_count):
            cell = self._cell(0, c)
            if cell and keyword in cell.text:
                return c
        return None

    def get_cell_text(self, r: int, c: int) -> str:
        """获取 (r, c) 单元格文本 (考虑合并)."""
        cell = self._cell(r, c)
        return cell.text if cell else ""

    def get_row_texts(self, r: int) -> list[str]:
        """获取第 r 行所有单元格文本."""
        return [self.get_cell_text(r, c) for c in range(self.table.col_count)]

    def get_column_texts(self, c: int, *, skip_header: bool = True) -> list[str]:
        """获取第 c 列所有数据单元格文本."""
        start = 1 if skip_header and self.table.row_count > 1 else 0
        return [self.get_cell_text(r, c) for r in range(start, self.table.row_count)]

    def collect_numeric_column(self, c: int, *, skip_header: bool = True) -> list[tuple[int, Decimal | None, str]]:
        """收集第 c 列的数值 (行号, 解析后的 Decimal, 原始文本)."""
        start = 1 if skip_header and self.table.row_count > 1 else 0
        out: list[tuple[int, Decimal | None, str]] = []
        for r in range(start, self.table.row_count):
            text = self.get_cell_text(r, c)
            out.append((r, to_decimal(text), text))
        return out

    def _cell(self, r: int, c: int):
        """获取 (r, c) 处的 cell, 优先用 grid, 回退到 find_cell_at."""
        if self.grid is not None:
            return cell_at(self.grid, r, c)
        return find_cell_at(self.table, r, c)
