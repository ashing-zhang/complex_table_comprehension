"""多级表头解析 + 字段继承 (TECHNICAL_SOLUTION.md 第 14-15 章).

生成逻辑列路径 ColumnPath = list[str], 例如:
  ["销售额", "2025", "1月"]

字段继承: 视觉空白的单元格可能继承上方/左侧的字段, 但只能作为候选语义,
保留来源与置信度, 不无条件覆盖原始数据.
"""

from __future__ import annotations

from src.table.grid import build_grid, cell_at
from src.table.models import Cell, Table


def resolve_column_paths(table: Table, *, header_row_count: int | None = None) -> list[list[str]]:
    """解析多级表头, 为每一列生成逻辑路径.

    Args:
        table: Canonical Table.
        header_row_count: 表头行数, 默认取 table.header_row_count.

    Returns:
        list[list[str]]: 长度等于 col_count 的列表, 每项为该列的路径.
    """
    hc = header_row_count if header_row_count is not None else table.header_row_count
    hc = max(1, hc)
    if table.row_count < hc:
        hc = table.row_count

    try:
        grid = build_grid(table)
    except Exception:
        # grid 构建失败时退化为每列首行文本.
        grid = None

    paths: list[list[str]] = []
    for c in range(table.col_count):
        path: list[str] = []
        for r in range(hc):
            text = ""
            if grid is not None:
                cell = cell_at(grid, r, c)
                text = cell.text if cell else ""
            else:
                # 退化: 找占用 (r, c) 的 cell.
                for cell in table.cells:
                    if cell.occupies(r, c):
                        text = cell.text
                        break
            text = (text or "").strip()
            if text and text not in path:
                path.append(text)
        paths.append(path)

    # 缓存到 table.
    table.column_paths = paths
    return paths


def infer_inherited_field(table: Table, r: int, c: int, *, confidence: float = 0.5) -> tuple[str, float] | None:
    """推断 (r, c) 处可能继承的"类别"字段 (TECHNICAL_SOLUTION.md 第 15 章).

    返回 (text, confidence) 或 None. 仅作为候选语义, 调用方须保留来源.
    """
    # 优先向上查找第一个非空单元格 (同列), 视为继承的类别.
    for rr in range(r - 1, -1, -1):
        for cell in table.cells:
            if cell.occupies(rr, c) and cell.text.strip():
                return cell.text.strip(), confidence
    return None
