"""Prompt 子包 (TECHNICAL_SOLUTION.md 第 23-26 章).

所有 Prompt 版本化, 不散落在 Python 业务代码中.
"""

from src.prompts.extract_prompt import build_extract_prompt
from src.prompts.keyword_prompt import build_keyword_prompt
from src.prompts.repair_prompt import build_repair_prompt
from src.prompts.structure_prompt import build_structure_prompt
from src.prompts.thinking_prompt import build_thinking_prompt

__all__ = [
    "build_structure_prompt",
    "build_extract_prompt",
    "build_thinking_prompt",
    "build_repair_prompt",
    "build_keyword_prompt",
]
