"""确定性计算器 (TECHNICAL_SOLUTION.md 第 18 章).

LLM 负责语义理解和找数据, Python 负责精确数值计算 / 排序 / 格式归一.
支持: add / subtract / multiply / divide / ratio / growth_rate /
      filter / sort / argmax / argmin / count / format.
"""

from __future__ import annotations

from decimal import Decimal
from typing import Any

from src.observability.logger import get_logger
from src.table.models import ErrorCode, TableAgentError
from src.table.normalizer import parse_percent, to_decimal

logger = get_logger("calculator")


class Calculator:
    """确定性计算器."""

    def add(self, values: list[Decimal | float | int | None]) -> Decimal:
        """求和 (忽略 None)."""
        total = Decimal("0")
        for v in values:
            if v is None:
                continue
            total += self._to_dec(v)
        return total

    def subtract(self, values: list[Decimal | float | int | None]) -> Decimal:
        """依次求差 (a - b - c ...)."""
        nums = [self._to_dec(v) for v in values if v is not None]
        if not nums:
            return Decimal("0")
        result = nums[0]
        for n in nums[1:]:
            result -= n
        return result

    def multiply(self, values: list[Decimal | float | int | None]) -> Decimal:
        """连乘."""
        result = Decimal("1")
        any_val = False
        for v in values:
            if v is None:
                continue
            result *= self._to_dec(v)
            any_val = True
        return result if any_val else Decimal("0")

    def divide(self, values: list[Decimal | float | int | None]) -> Decimal:
        """依次相除 a / b / c ...."""
        nums = [self._to_dec(v) for v in values if v is not None]
        if not nums or nums[0] == 0:
            raise TableAgentError(ErrorCode.CALCULATION_ERROR, "divide by zero or empty")
        result = nums[0]
        for n in nums[1:]:
            if n == 0:
                raise TableAgentError(ErrorCode.CALCULATION_ERROR, "divide by zero")
            result /= n
        return result

    def ratio(self, a: Decimal | float | int | None, b: Decimal | float | int | None) -> Decimal:
        """比例 a / b."""
        bb = self._to_dec(b)
        if bb == 0:
            raise TableAgentError(ErrorCode.CALCULATION_ERROR, "ratio by zero")
        return self._to_dec(a) / bb

    def growth_rate(self, current: Decimal | float | int | None, previous: Decimal | float | int | None) -> Decimal:
        """增长率 (current - previous) / previous."""
        p = self._to_dec(previous)
        if p == 0:
            raise TableAgentError(ErrorCode.CALCULATION_ERROR, "growth_rate by zero previous")
        return (self._to_dec(current) - p) / p

    def argmax(self, values: list[tuple[Any, Decimal | None]]) -> tuple[Any, Decimal]:
        """返回最大值的 (key, value)."""
        eligible = [(k, self._to_dec(v)) for k, v in values if v is not None]
        if not eligible:
            raise TableAgentError(ErrorCode.VALUE_NOT_FOUND, "argmax over empty values")
        return max(eligible, key=lambda kv: kv[1])

    def argmin(self, values: list[tuple[Any, Decimal | None]]) -> tuple[Any, Decimal]:
        """返回最小值的 (key, value)."""
        eligible = [(k, self._to_dec(v)) for k, v in values if v is not None]
        if not eligible:
            raise TableAgentError(ErrorCode.VALUE_NOT_FOUND, "argmin over empty values")
        return min(eligible, key=lambda kv: kv[1])

    def sort(self, values: list[tuple[Any, Decimal | None]], *, descending: bool = False) -> list[tuple[Any, Decimal]]:
        """排序, 返回 [(key, value), ...]."""
        eligible = [(k, self._to_dec(v)) for k, v in values if v is not None]
        return sorted(eligible, key=lambda kv: kv[1], reverse=descending)

    def count(self, values: list[Any]) -> int:
        """计数 (非空元素个数)."""
        return sum(1 for v in values if v is not None and str(v).strip() != "")

    def execute_plan(self, plan: dict[str, Any], table_text_lookup: dict[tuple[int, int], str] | None = None) -> Decimal | int | list[Decimal]:
        """执行 LLM 生成的计算计划.

        plan 字段: {operation, inputs: [{row, col, text}], output_format}.
        table_text_lookup: (row, col) -> 原始文本, 用于校验 inputs 与表格一致.

        Returns:
            计算结果 (Decimal / int; filter 操作返回 Decimal 列表).
        """
        op = str(plan.get("operation", "")).lower()
        inputs = plan.get("inputs", []) or []
        # 校验 inputs 与表格文本一致 (可选, 仅供 trace).
        if table_text_lookup is not None:
            for item in inputs:
                r = item.get("row")
                c = item.get("col")
                t = str(item.get("text", "")).strip()
                actual = table_text_lookup.get((r, c), "").strip()
                if t and actual and t != actual and t.replace(",", "") != actual.replace(",", ""):
                    logger.warning("plan input mismatch at (%s,%s): plan=%r table=%r", r, c, t, actual)

        # 抽取数值: 优先用文本里的数值 (与 table 一致), 兼容百分比.
        nums: list[Decimal | None] = []
        for item in inputs:
            t = str(item.get("text", ""))
            p = parse_percent(t)
            nums.append(p if p is not None else to_decimal(t))

        if op in ("sum", "add"):
            return self.add(nums)
        if op in ("subtract", "sub", "diff"):
            return self.subtract(nums)
        if op in ("multiply", "mul", "product"):
            return self.multiply(nums)
        if op in ("divide", "div"):
            return self.divide(nums)
        if op in ("ratio", "proportion"):
            if len([n for n in nums if n is not None]) < 2:
                raise TableAgentError(ErrorCode.CALCULATION_ERROR, "ratio needs 2 values")
            return self.ratio(nums[0], nums[1])
        if op in ("growth_rate", "growth", "yoy", "mom"):
            if len([n for n in nums if n is not None]) < 2:
                raise TableAgentError(ErrorCode.CALCULATION_ERROR, "growth_rate needs 2 values")
            return self.growth_rate(nums[0], nums[1])
        if op in ("count", "len"):
            return self.count([i.get("text") for i in inputs])
        if op in ("format", "normalize"):
            if not nums:
                raise TableAgentError(ErrorCode.CALCULATION_ERROR, "format needs 1 value")
            if len(nums) > 1:
                logger.warning("format op received %d values, returning only first", len(nums))
            return self._to_dec(nums[0])
        if op in ("argmax", "max"):
            ks = [(i.get("row"), to_decimal(i.get("text"))) for i in inputs]
            return self.argmax(ks)[1]
        if op in ("argmin", "min"):
            ks = [(i.get("row"), to_decimal(i.get("text"))) for i in inputs]
            return self.argmin(ks)[1]
        if op in ("filter", "locate", "select"):
            # 纯定位类操作: 返回所有可解析的输入数值 (与输入顺序一致).
            values = [self._to_dec(n) for n in nums if n is not None]
            if not values:
                raise TableAgentError(ErrorCode.VALUE_NOT_FOUND, "filter matched no numeric input")
            return values
        raise TableAgentError(ErrorCode.CALCULATION_ERROR, f"unknown operation: {op}")

    def _to_dec(self, v: Decimal | float | int | None) -> Decimal:
        """将任意数值转为 Decimal."""
        if v is None:
            return Decimal("0")
        if isinstance(v, Decimal):
            return v
        if isinstance(v, int):
            return Decimal(v)
        if isinstance(v, float):
            return Decimal(str(v))
        return self._to_dec(to_decimal(str(v)))
