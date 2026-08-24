"""表格视觉解析器 (TECHNICAL_SOLUTION.md 第 10-11 章).

将图像 + 题目指令发送给 Qwen, 解析为 Canonical Table Representation.
负责:
- structure 两阶段恢复 (视觉识别 + 结构推理)
- JSON schema 校验 (交给 validation 层)
- 有限次数 repair

模型只生成中间 JSON, 程序负责 schema validation / normalization / formatting.
"""

from __future__ import annotations

import json
from typing import Any

from src.observability.logger import get_logger
from src.observability.trace import TraceContext
from src.prompts.repair_prompt import build_repair_prompt
from src.prompts.structure_prompt import build_structure_prompt
from src.table.models import Cell, ErrorCode, Table, TableAgentError
from src.vision.qwen_client import QwenClient, get_qwen_client
from src.vision.vision_parser import extract_json

logger = get_logger("table_parser")


class TableParser:
    """表格视觉解析器: image + question -> Canonical Table."""

    def __init__(self, client: QwenClient | None = None, *, repair_max_retries: int = 2) -> None:
        """初始化解析器.

        Args:
            client: QwenClient, 默认使用全局单例.
            repair_max_retries: JSON repair 最大重试次数.
        """
        self.client = client or get_qwen_client()
        self.repair_max_retries = repair_max_retries

    def parse_structure(
        self,
        image_paths: list[str],
        question_text: str,
        *,
        trace: TraceContext | None = None,
        local_hint: str | None = None,
    ) -> Table:
        """解析表格结构, 返回 Canonical Table.

        Args:
            image_paths: 表格图像路径 (可为整页或裁剪后的表格区域).
            question_text: 题目文本.
            trace: 追踪上下文.
            local_hint: 局部结构提示 (例如 "前 1 行前 1 列").

        Returns:
            Table: 含 row_count/col_count/cells.
        """
        system, user_prompt = build_structure_prompt(question_text, local_hint=local_hint)

        last_error: str | None = None
        raw_output = ""
        for attempt in range(self.repair_max_retries + 1):
            try:
                raw_output = self.client.chat_with_images(
                    image_paths=image_paths,
                    prompt=user_prompt,
                    system=system,
                    trace=trace,
                    stage=f"structure_v1{'_repair' if attempt else ''}",
                )
                if trace:
                    trace.event("structure_raw", attempt=attempt, output=raw_output[:1000])
                table = self._build_table_from_output(raw_output)
                if trace:
                    trace.event("structure_parsed", row_count=table.row_count, col_count=table.col_count, cells=len(table.cells))
                return table
            except TableAgentError as exc:
                last_error = str(exc)
                logger.warning("structure parse attempt %d failed: %s", attempt, exc)
                if attempt >= self.repair_max_retries:
                    break
                # repair: 用上次的错误信息生成修复提示.
                repair_system, repair_user = build_repair_prompt(raw_output, last_error)
                try:
                    raw_output = self.client.chat_with_images(
                        image_paths=image_paths,
                        prompt=repair_user,
                        system=repair_system,
                        trace=trace,
                        stage="structure_repair",
                    )
                except Exception as exc2:  # noqa: BLE001
                    last_error = f"repair call failed: {exc2}"
                    continue

        raise TableAgentError(ErrorCode.INVALID_JSON, f"structure parse failed: {last_error}")

    def _build_table_from_output(self, raw: str) -> Table:
        """从模型输出构造 Table (含基础 schema 校验)."""
        data = extract_json(raw)
        if not isinstance(data, dict):
            raise TableAgentError(ErrorCode.INVALID_JSON, "structure output is not an object")
        if "row_count" not in data or "col_count" not in data or "cells" not in data:
            raise TableAgentError(ErrorCode.STRUCTURE_INVALID, "structure output missing required keys")

        rc = int(data["row_count"])
        cc = int(data["col_count"])
        cells_raw = data["cells"]
        if not isinstance(cells_raw, list):
            raise TableAgentError(ErrorCode.STRUCTURE_INVALID, "cells is not a list")

        cells: list[Cell] = []
        for i, c in enumerate(cells_raw):
            if not isinstance(c, dict):
                continue
            if "text" not in c or "row" not in c or "col" not in c:
                raise TableAgentError(ErrorCode.STRUCTURE_INVALID, f"cell {i} missing required fields")
            text = str(c.get("text", "")).strip()
            row = int(c.get("row", 0))
            col = int(c.get("col", 0))
            rowspan = max(1, int(c.get("rowspan", 1) or 1))
            colspan = max(1, int(c.get("colspan", 1) or 1))
            cells.append(Cell(text=text, row=row, col=col, rowspan=rowspan, colspan=colspan))

        table = Table(row_count=rc, col_count=cc, cells=cells)
        return table

    def parse_extract_raw(
        self,
        image_paths: list[str],
        question_text: str,
        *,
        trace: TraceContext | None = None,
        table_hint: str | None = None,
    ) -> dict[str, Any]:
        """解析 extract 任务: 让模型先定位再输出 evidence + answer."""
        from src.prompts.extract_prompt import build_extract_prompt

        system, user_prompt = build_extract_prompt(question_text, table_hint=table_hint)
        raw = self.client.chat_with_images(
            image_paths=image_paths,
            prompt=user_prompt,
            system=system,
            trace=trace,
            stage="extract_v1",
        )
        if trace:
            trace.event("extract_raw", output=raw[:1000])
        data = extract_json(raw)
        if not isinstance(data, dict):
            raise TableAgentError(ErrorCode.INVALID_JSON, "extract output is not an object")
        return data

    def parse_thinking_plan(
        self,
        image_paths: list[str],
        question_text: str,
        *,
        trace: TraceContext | None = None,
        table_hint: str | None = None,
    ) -> dict[str, Any]:
        """解析 thinking 任务: 让模型生成计算计划, 由 Python 执行."""
        from src.prompts.thinking_prompt import build_thinking_prompt

        system, user_prompt = build_thinking_prompt(question_text, table_hint=table_hint)
        raw = self.client.chat_with_images(
            image_paths=image_paths,
            prompt=user_prompt,
            system=system,
            trace=trace,
            stage="thinking_v1",
        )
        if trace:
            trace.event("thinking_raw", output=raw[:1000])
        data = extract_json(raw)
        if not isinstance(data, dict):
            raise TableAgentError(ErrorCode.INVALID_JSON, "thinking output is not an object")
        return data
