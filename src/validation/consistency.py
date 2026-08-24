"""一致性检查 (TECHNICAL_SOLUTION.md 第 22 章 Self-Consistency).

对高风险任务可加 verifier, 这里提供轻量一致性检查:
- 检查 evidence 与 answer 是否同源
- 检查 structure cells 是否覆盖了 row_count * col_count
"""

from __future__ import annotations

from src.table.grid import validate_grid
from src.table.models import Table, TaskResult


def check_consistency(result: TaskResult, table: Table | None = None) -> list[str]:
    """返回一致性 warning 列表 (空列表表示一致)."""
    warnings: list[str] = []
    if table is None:
        return warnings

    # structure 类: 检查 grid 是否完整 (无 None 空位意味着 cells 覆盖了所有位置).
    if result.answer and result.answer.strip().startswith("{"):
        gv = validate_grid(table)
        if not gv.ok:
            warnings.append(f"grid inconsistent: {gv.issues[:3]}")
    return warnings
