"""重试策略 (TECHNICAL_SOLUTION.md 第 21, 49 章).

只对临时错误 (timeout / 429 / 5xx) 重试, 指数退避.
不对 invalid question / file not found / invalid JSON schema 无限重试.
"""

from __future__ import annotations

import time
from typing import Any, Callable, TypeVar

from src.observability.logger import get_logger
from src.table.models import ErrorCode, TableAgentError

logger = get_logger("retry")

T = TypeVar("T")


def with_retry(
    func: Callable[..., T],
    *args: Any,
    max_retries: int = 2,
    base_delay: float = 1.0,
    **kwargs: Any,
) -> T:
    """带指数退避的重试包装.

    Args:
        func: 可调用对象.
        *args, **kwargs: 传给 func 的参数.
        max_retries: 最大重试次数 (总尝试 = max_retries + 1).
        base_delay: 基础退避秒数.

    Returns:
        func 的返回值.

    Raises:
        TableAgentError: 重试耗尽后仍失败.
    """
    last_exc: Exception | None = None
    for attempt in range(max_retries + 1):
        try:
            return func(*args, **kwargs)
        except TableAgentError as exc:
            last_exc = exc
            # 非临时错误不重试.
            retryable_codes = {
                ErrorCode.MODEL_ERROR,
                ErrorCode.PDF_PARSE_ERROR,
                ErrorCode.IMAGE_ERROR,
            }
            if exc.code not in retryable_codes or attempt >= max_retries:
                raise
            delay = min(base_delay * (2 ** attempt), 8.0)
            logger.warning("retry attempt %d/%d after %.1fs: %s", attempt + 1, max_retries, delay, exc)
            time.sleep(delay)
        except Exception as exc:  # noqa: BLE001
            last_exc = exc
            if attempt >= max_retries:
                raise
            delay = min(base_delay * (2 ** attempt), 8.0)
            logger.warning("retry attempt %d/%d after %.1fs: %s", attempt + 1, max_retries, delay, exc)
            time.sleep(delay)
    raise TableAgentError(ErrorCode.MODEL_ERROR, f"retry exhausted: {last_exc}")
