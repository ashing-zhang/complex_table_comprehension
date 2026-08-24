"""文本/数值归一化 (TECHNICAL_SOLUTION.md 第 17-19 章).

将表格文本归一化为结构化数值: 整数 / Decimal / 百分比 / 金额 / 单位.
最终答案格式化也在此完成 (去除千分位逗号等).
"""

from __future__ import annotations

import re
from decimal import Decimal, InvalidOperation
from typing import Any

from src.table.models import Table

# 千分位逗号 / 空白.
_COMMA_RE = re.compile(r"(?<=\d),(?=\d)")
# 中文数字单位.
_CN_UNIT_FACTORS: dict[str, Decimal] = {
    "万": Decimal("10000"),
    "万元": Decimal("10000"),
    "亿": Decimal("100000000"),
    "亿元": Decimal("100000000"),
    "千": Decimal("1000"),
    "千吨": Decimal("1000"),
    "百万": Decimal("1000000"),
}
# 数字提取.
_NUMBER_RE = re.compile(r"[-+]?\d[\d,]*\.?\d*")


def normalize_number_text(text: str) -> str:
    """去除千分位逗号与多余空白, 返回干净数字字符串."""
    if text is None:
        return ""
    s = str(text).strip()
    s = _COMMA_RE.sub("", s)
    return s


def to_decimal(text: str) -> Decimal | None:
    """将文本解析为 Decimal, 失败返回 None."""
    if text is None:
        return None
    s = str(text).strip()
    if not s:
        return None
    # 提取首个数字串.
    m = _NUMBER_RE.search(s)
    if not m:
        return None
    cleaned = normalize_number_text(m.group(0))
    try:
        return Decimal(cleaned)
    except (InvalidOperation, ValueError):
        return None


def parse_percent(text: str) -> Decimal | None:
    """解析百分比, 12.5% -> Decimal('0.125')."""
    if text is None:
        return None
    s = str(text).strip()
    if "%" not in s and "％" not in s:
        return None
    s = s.replace("％", "%").replace("%", "")
    d = to_decimal(s)
    if d is None:
        return None
    return d / Decimal("100")


def parse_unit_value(text: str) -> tuple[Decimal | None, str | None]:
    """解析带单位的数值, 返回 (value, unit).

    例如 "125万元" -> (Decimal(125), "万元"); "300000元" -> (Decimal(300000), "元").
    """
    if text is None:
        return None, None
    s = str(text).strip()
    d = to_decimal(s)
    if d is None:
        return None, None
    # 查找单位.
    unit = None
    for u in _CN_UNIT_FACTORS:
        if u in s:
            unit = u
            break
    if unit is None:
        # 简单单字单位.
        for u in ("元", "吨", "个", "件", "%"):
            if u in s:
                unit = u
                break
    return d, unit


def normalize_to_yuan(value: Decimal, unit: str | None) -> Decimal:
    """将带单位的金额归一为"元"."""
    if unit is None:
        return value
    factor = _CN_UNIT_FACTORS.get(unit)
    if factor is None:
        return value
    return value * factor


def format_number(value: Decimal | int | float | None, *, output_format: str | None = None) -> str:
    """按 answer_format 格式化数值.

    - number: 去除千分位逗号的纯数字.
    - percent: 百分比字符串 (例如 "12.5%").
    - 默认: 去除千分位逗号.
    """
    if value is None:
        return ""
    if isinstance(value, Decimal):
        # format(..., "f") 避免科学计数法, 再去除小数末尾多余 0.
        s = format(value, "f")
        if "." in s:
            s = s.rstrip("0").rstrip(".")
    elif isinstance(value, float):
        s = f"{value:g}"
    else:
        s = str(value)
    s = s.replace(",", "")
    if output_format == "percent" or output_format == "percentage":
        # 假设 value 已经是百分数 (例如 12.5), 输出 "12.5%".
        s = f"{s}%"
    return s


def normalize_table_text(table: Table) -> Table:
    """对表格所有 cell 文本做轻量归一 (去首尾空白/统一空白字符), 返回 table 自身."""
    for cell in table.cells:
        if cell.text:
            cell.text = re.sub(r"\s+", " ", cell.text).strip()
    return table
