"""合并单元格解析 (TECHNICAL_SOLUTION.md 第 12.1 章).

提供查找合并单元格、获取覆盖区域等工具.
"""

from __future__ import annotations

from src.table.models import Cell, Table


def merged_cells(table: Table) -> list[Cell]:
    """返回所有有合并的单元格 (rowspan>1 或 colspan>1)."""
    return [c for c in table.cells if c.rowspan > 1 or c.colspan > 1]


def find_cell_at(table: Table, r: int, c: int) -> Cell | None:
    """查找占用 (r, c) 位置的单元格 (考虑合并覆盖范围)."""
    for cell in table.cells:
        if cell.occupies(r, c):
            return cell
    return None


def coverage_cells(table: Table) -> dict[tuple[int, int], Cell]:
    """构造 (r, c) -> Cell 的映射, 包括被合并覆盖的位置."""
    cov: dict[tuple[int, int], Cell] = {}
    for cell in table.cells:
        for r in range(cell.row, cell.row + cell.rowspan):
            for c in range(cell.col, cell.col + cell.colspan):
                cov[(r, c)] = cell
    return cov
