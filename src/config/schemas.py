"""输入/输出 Schema 定义.

定义 tests.xlsx 与 submission.xlsx 的列约束, 供 loader/validator 复用.
"""

from __future__ import annotations

# tests.xlsx 必填列.
QUESTION_REQUIRED_COLUMNS = ["id", "file_name", "question_type", "question"]
# tests.xlsx 可选列.
QUESTION_OPTIONAL_COLUMNS = ["table_hint", "answer_format", "answer"]

# submission.xlsx 必填列.
SUBMISSION_COLUMNS = ["id", "answer"]

# 合法的 question_type 取值.
VALID_QUESTION_TYPES = {"structure", "extract", "thinking"}

# 合法的 answer_format 取值 (None 也允许).
VALID_ANSWER_FORMATS = {"string", "number", "json", "json_array", None}

# 默认每道题在无法作答时的兜底答案.
EMPTY_ANSWER = ""
