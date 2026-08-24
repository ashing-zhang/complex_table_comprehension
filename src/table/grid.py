"""Grid 重建与冲突检测 (TECHNICAL_SOLUTION.md 第 12 章).

将 LLM 输出的 cells 重新构建为逻辑网格, 检测 cell overlap / 越界 / 非法合并.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from src.table.models import Cell, Table, TableAgentError
from src.table.models import ErrorCode


@dataclass
class GridValidation:
    """Grid 校验结果."""

    ok: bool
    issues: list[str]
    grid: list[list[Cell | None]] | None = None


def build_grid(table: Table) -> list[list[Cell | None]]:
    """根据 cells 构造 row_count x col_count 的逻辑网格.

    每个 (r, c) 位置存放占用它的 Cell 引用, 或 None.
    Raises:
        TableAgentError(STRUCTURE_INVALID): 越界或 overlap 冲突时抛出.
    """
    rc = table.row_count
    cc = table.col_count
    if rc <= 0 or cc <= 0:
        raise TableAgentError(ErrorCode.STRUCTURE_INVALID, f"non-positive row/col count: {rc}x{cc}")

    grid: list[list[Cell | None]] = [[None for _ in range(cc)] for _ in range(rc)]

    for cell in table.cells:
        if cell.row < 0 or cell.col < 0:
            raise TableAgentError(ErrorCode.STRUCTURE_INVALID, f"cell negative index: ({cell.row},{cell.col})")
        if cell.rowspan < 1 or cell.colspan < 1:
            raise TableAgentError(ErrorCode.STRUCTURE_INVALID, f"cell invalid span: rowspan={cell.rowspan} colspan={cell.colspan}")
        if cell.row + cell.rowspan > rc or cell.col + cell.colspan > cc:
            raise TableAgentError(
                ErrorCode.STRUCTURE_INVALID,
                f"cell out of bounds: ({cell.row},{cell.col}) span=({cell.rowspan},{cell.colspan}) grid=({rc}x{cc})",
            )
        # 检测 overlap 冲突.
        for r in range(cell.row, cell.row + cell.rowspan):
            for c in range(cell.col, cell.col + cell.colspan):
                if grid[r][c] is not None:
                    raise TableAgentError(
                        ErrorCode.STRUCTURE_INVALID,
                        f"cell overlap at ({r},{c}): {grid[r][c]!r} vs {cell!r}",
                    )
                grid[r][c] = cell
    return grid


def validate_grid(table: Table) -> GridValidation:
    """非抛出式校验: 返回 GridValidation, issues 列出所有问题."""
    issues: list[str] = []
    rc = table.row_count
    cc = table.col_count
    if rc <= 0 or cc <= 0:
        return GridValidation(ok=False, issues=[f"non-positive row/col count: {rc}x{cc}"], grid=None)

    grid: list[list[Cell | None]] = [[None for _ in range(cc)] for _ in range(rc)]
    for cell in table.cells:
        if cell.row < 0 or cell.col < 0:
            issues.append(f"cell negative index: ({cell.row},{cell.col})")
            continue
        if cell.rowspan < 1 or cell.colspan < 1:
            issues.append(f"cell invalid span at ({cell.row},{cell.col}): rowspan={cell.rowspan} colspan={cell.colspan}")
            continue
        if cell.row + cell.rowspan > rc or cell.col + cell.colspan > cc:
            issues.append(
                f"cell out of bounds at ({cell.row},{cell.col}) span=({cell.rowspan},{cell.colspan}) grid=({rc}x{cc})"
            )
            continue
        for r in range(cell.row, cell.row + cell.rowspan):
            for c in range(cell.col, cell.col + cell.colspan):
                if grid[r][c] is not None:
                    issues.append(f"cell overlap at ({r},{c})")
                else:
                    grid[r][c] = cell
    return GridValidation(ok=(not issues), issues=issues, grid=grid if not issues else None)


def grid_to_text(grid: list[list[Cell | None]]) -> str:
    """将网格转为可读文本 (debug 用)."""
    lines: list[str] = []
    for r, row in enumerate(grid):
        parts = []
        for c, cell in enumerate(row):
            parts.append((cell.text if cell else "") or "-")
        lines.append(f"r{r}: " + " | ".join(parts))
    return "\n".join(lines)


def cell_at(grid: list[list[Cell | None]], r: int, c: int) -> Cell | None:
    """安全获取 (r, c) 处的 cell."""
    if 0 <= r < len(grid) and 0 <= c < len(grid[0]):
        return grid[r][c]
    return None
