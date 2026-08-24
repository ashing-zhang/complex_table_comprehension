"""Qwen 多模态客户端 (TECHNICAL_SOLUTION.md 第 10 章).

通过阿里云百炼 OpenAI 兼容端点调用千问系列模型.
禁止业务代码直接调用 SDK, 统一通过 QwenClient.
"""

from __future__ import annotations

import base64
import os
import time
from pathlib import Path
from typing import Any

from src.config.settings import get_settings
from src.observability.logger import get_logger
from src.observability.trace import TraceContext
from src.table.models import ErrorCode, TableAgentError

logger = get_logger("qwen_client")

# 兼容的图片扩展名.
_IMAGE_EXTS = {".png", ".jpg", ".jpeg", ".webp", ".bmp", ".tif", ".tiff"}


class QwenClient:
    """Qwen 多模态客户端封装.

    封装 OpenAI 兼容 SDK, 提供:
    - 超时 / 重试 / 限流
    - 图像 base64 编码
    - 结构化 JSON 输出
    - 调用日志与 trace
    """

    def __init__(
        self,
        api_key: str | None = None,
        base_url: str | None = None,
        vision_model: str | None = None,
        reasoning_model: str | None = None,
        timeout: int | None = None,
        max_retries: int = 2,
    ) -> None:
        """初始化客户端.

        参数默认从 Settings 读取; 显式参数优先.
        """
        settings = get_settings()
        self.api_key = api_key or settings.model.api_key or os.getenv("DASHSCOPE_API_KEY", "")
        self.base_url = base_url or settings.model.base_url
        self.vision_model = vision_model or settings.model.vision_model
        self.reasoning_model = reasoning_model or settings.model.reasoning_model
        self.timeout = timeout or settings.model.request_timeout
        self.max_retries = max_retries or settings.pipeline.max_retries
        self.temperature = settings.model.temperature
        self.max_tokens = settings.model.max_tokens

        if not self.api_key:
            raise TableAgentError(ErrorCode.MODEL_ERROR, "DASHSCOPE_API_KEY not set")

        # 安全检查: provider 必须为阿里云 (TECHNICAL_SOLUTION.md 第 52 章).
        if "aliyuncs.com" not in self.base_url:
            logger.warning("base_url not from aliyun: %s", self.base_url)

        try:
            from openai import OpenAI
        except ImportError as exc:  # pragma: no cover
            raise TableAgentError(ErrorCode.MODEL_ERROR, "openai sdk not installed") from exc

        self._client = OpenAI(api_key=self.api_key, base_url=self.base_url, timeout=self.timeout)
        logger.info("QwenClient ready: vision=%s reasoning=%s", self.vision_model, self.reasoning_model)

    def _encode_image(self, image_path: str) -> str:
        """将本地图像编码为 data URL."""
        p = Path(image_path)
        if not p.exists():
            raise TableAgentError(ErrorCode.IMAGE_ERROR, f"image not found: {image_path}")
        ext = p.suffix.lower()
        mime = "image/png" if ext == ".png" else "image/jpeg" if ext in (".jpg", ".jpeg") else "image/png"
        with open(p, "rb") as f:
            b64 = base64.b64encode(f.read()).decode("utf-8")
        return f"data:{mime};base64,{b64}"

    def chat(
        self,
        messages: list[dict[str, Any]],
        *,
        model: str | None = None,
        temperature: float | None = None,
        trace: TraceContext | None = None,
        stage: str = "chat",
    ) -> str:
        """纯文本对话.

        Args:
            messages: OpenAI 风格 messages.
            model: 模型名, 默认 reasoning_model.
            temperature: 温度, 默认客户端配置.
            trace: 追踪上下文.
            stage: 阶段标签 (用于 trace).

        Returns:
            模型回复文本.
        """
        return self._call(messages, model or self.reasoning_model, temperature, trace, stage, image_paths=None)

    def chat_with_images(
        self,
        image_paths: list[str],
        prompt: str,
        *,
        model: str | None = None,
        temperature: float | None = None,
        system: str | None = None,
        trace: TraceContext | None = None,
        stage: str = "vision",
    ) -> str:
        """多模态对话: 将图像 + 文本一起发送.

        Args:
            image_paths: 本地图像路径列表 (取最后一张或多张).
            prompt: 用户文本指令.
            model: 模型名, 默认 vision_model.
            temperature: 温度.
            system: 可选 system prompt.
            trace: 追踪上下文.
            stage: 阶段标签.

        Returns:
            模型回复文本.
        """
        messages: list[dict[str, Any]] = []
        if system:
            messages.append({"role": "system", "content": system})

        content: list[dict[str, Any]] = []
        for img in image_paths:
            content.append({"type": "image_url", "image_url": {"url": self._encode_image(img)}})
        content.append({"type": "text", "text": prompt})
        messages.append({"role": "user", "content": content})

        return self._call(messages, model or self.vision_model, temperature, trace, stage, image_paths=image_paths)

    def _call(
        self,
        messages: list[dict[str, Any]],
        model: str,
        temperature: float | None,
        trace: TraceContext | None,
        stage: str,
        image_paths: list[str] | None,
    ) -> str:
        """底层调用, 带指数退避重试."""
        last_exc: Exception | None = None
        for attempt in range(1, self.max_retries + 2):
            t0 = time.time()
            try:
                resp = self._client.chat.completions.create(
                    model=model,
                    messages=messages,
                    temperature=self.temperature if temperature is None else temperature,
                    max_tokens=self.max_tokens,
                )
                latency = time.time() - t0
                text = resp.choices[0].message.content or ""
                usage = getattr(resp, "usage", None)
                tokens = getattr(usage, "total_tokens", 0) if usage else 0
                if trace:
                    trace.model_call(model=model, stage=stage, latency=round(latency, 3), tokens=tokens, attempt=attempt)
                logger.info("qwen %s ok in %.2fs (model=%s, tokens=%s, attempt=%d)", stage, latency, model, tokens, attempt)
                return text
            except Exception as exc:  # noqa: BLE001
                last_exc = exc
                # 判断是否可重试: 超时 / 429 / 5xx.
                msg = str(exc).lower()
                retryable = any(k in msg for k in ("timeout", "timed out", "429", "rate limit", "server", "502", "503", "504", "connection"))
                logger.warning("qwen %s attempt %d failed: %s (retryable=%s)", stage, attempt, exc, retryable)
                if not retryable or attempt > self.max_retries:
                    break
                time.sleep(min(2 ** (attempt - 1), 8))
        raise TableAgentError(ErrorCode.MODEL_ERROR, f"qwen call failed after retries: {last_exc}")


_CLIENT: QwenClient | None = None


def get_qwen_client() -> QwenClient:
    """获取全局 QwenClient 单例."""
    global _CLIENT
    if _CLIENT is None:
        _CLIENT = QwenClient()
    return _CLIENT
