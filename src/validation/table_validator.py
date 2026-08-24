"""Table 结构校验器 (TECHNICAL_SOLUTION.md 第 20.2 章).

检查 row_count/col_count > 0, row/col/span 范围, 检测 cell overlap.
"""

from __future__ import annotations

from src.table.grid import validate_grid
from src.table.models import Table


def validate_table(table: Table) -> tuple[bool, list[str]]:
    """校验 Canonical Table 的结构合法性.

    Returns:
        (ok, issues).
    """
    issues: list[str] = []
    if table.row_count <= 0:
        issues.append(f"row_count <= 0: {table.row_count}")
    if table.col_count <= 0:
        issues.append(f"col_count <= 0: {table.col_count}")
    if issues:
        return False, issues

    gv = validate_grid(table)
    return gv.ok, gv.issues
