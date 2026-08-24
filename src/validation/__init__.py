"""校验子包 (TECHNICAL_SOLUTION.md 第 20 章).

三层校验:
- Schema Validator: JSON 合法性 / 字段存在 / 字段类型
- Table Validator: 结构合法性 (row/col/span 范围, overlap)
- Answer Validator: 答案与表格 evidence 一致性, 计算输入合法性
"""

from src.validation.answer_validator import AnswerValidator, validate_answer
from src.validation.consistency import check_consistency
from src.validation.schema_validator import validate_structure_json, validate_task_result_schema
from src.validation.table_validator import validate_table

__all__ = [
    "AnswerValidator",
    "validate_answer",
    "check_consistency",
    "validate_structure_json",
    "validate_task_result_schema",
    "validate_table",
]
