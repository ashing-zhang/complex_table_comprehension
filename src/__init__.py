"""复杂表格视觉理解与问答系统.

本包实现基于阿里云千问 (Qwen) 多模态模型的复杂表格结构恢复、内容提取与推理计算.
按 TECHNICAL_SOLUTION.md 的设计, 视觉模型负责"看懂表格", Python 程序负责
"结构约束 / 计算 / 校验 / 提交".
"""

__version__ = "0.1.0"

# 将本地 .vendor 目录加入 sys.path 以便在没有系统级安装时使用第三方依赖.
import os
import sys

_VENDOR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), ".vendor")
if os.path.isdir(_VENDOR) and _VENDOR not in sys.path:
    sys.path.insert(0, _VENDOR)
