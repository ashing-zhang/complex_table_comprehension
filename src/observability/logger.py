"""统一日志器.

提供带结构化字段的 console logger, 同时写入到 data/debug/run.log.
"""

from __future__ import annotations

import logging
import sys
from pathlib import Path

from src.config.settings import PROJECT_ROOT, get_settings

_CONFIGURED = False


def _configure_root_logger() -> None:
    """配置根 logger 的格式与输出目标 (console + 文件)."""
    global _CONFIGURED
    if _CONFIGURED:
        return
    settings = get_settings()
    log_dir = PROJECT_ROOT / "data" / "debug"
    log_dir.mkdir(parents=True, exist_ok=True)
    log_file = log_dir / "run.log"

    fmt = logging.Formatter(
        "[%(asctime)s] [%(levelname)s] [%(name)s] %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    root = logging.getLogger()
    root.setLevel(logging.INFO)
    # 清理已有 handlers, 避免重复输出.
    for h in list(root.handlers):
        root.removeHandler(h)

    sh = logging.StreamHandler(sys.stdout)
    sh.setFormatter(fmt)
    root.addHandler(sh)

    fh = logging.FileHandler(log_file, encoding="utf-8")
    fh.setFormatter(fmt)
    root.addHandler(fh)

    _CONFIGURED = True


def get_logger(name: str) -> logging.Logger:
    """获取命名 logger, 自动初始化根配置."""
    _configure_root_logger()
    return logging.getLogger(name)
