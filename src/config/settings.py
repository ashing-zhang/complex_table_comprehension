"""全局配置加载.

合并 configs/default.yaml 与环境变量, 形成统一的 Settings 对象.
所有模块均通过 get_settings() 获取配置, 避免散落的硬编码.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path
from typing import Any

import yaml
from dotenv import load_dotenv

# 项目根目录: src/config/settings.py 上溯两级.
PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_CONFIG_PATH = PROJECT_ROOT / "configs" / "default.yaml"

# 在模块导入时加载项目根 .env, 使 os.getenv() 在 _apply_env_overrides() 中能读到.
# override=False (默认): 已存在的真实环境变量优先于 .env, 适配 CI/生产环境;
# 文件不存在时返回 False 不报错, 适配无 .env 的运行环境 (如纯环境变量部署).
load_dotenv(PROJECT_ROOT / ".env", override=False)


@dataclass
class ModelSettings:
    """模型相关配置."""

    provider: str = "aliyun"
    base_url: str = "https://dashscope.aliyuncs.com/compatible-mode/v1"
    vision_model: str = "qwen-vl-max-latest"
    reasoning_model: str = "qwen-plus"
    temperature: float = 0.0
    max_tokens: int = 4096
    request_timeout: int = 120
    api_key: str = ""


@dataclass
class PipelineSettings:
    """Pipeline 运行参数."""

    max_retries: int = 2
    enable_verifier: bool = False
    enable_cache: bool = True
    repair_max_retries: int = 2
    save_intermediate: bool = True
    save_images: bool = True
    page_top_k: int = 5
    table_top_k: int = 3
    pdf_dpi: int = 200
    max_image_long_side: int = 4096


@dataclass
class ConcurrencySettings:
    """并发控制."""

    max_workers: int = 4
    qwen_concurrency: int = 2


@dataclass
class DataPaths:
    """数据路径."""

    tests: str = "data/tests.xlsx"
    files: str = "data/files"
    output: str = "data/output/submission.xlsx"
    debug: str = "data/debug"


@dataclass
class Settings:
    """统一配置对象."""

    project_name: str = "table-agent"
    model: ModelSettings = field(default_factory=ModelSettings)
    pipeline: PipelineSettings = field(default_factory=PipelineSettings)
    concurrency: ConcurrencySettings = field(default_factory=ConcurrencySettings)
    data: DataPaths = field(default_factory=DataPaths)
    config_path: str = str(DEFAULT_CONFIG_PATH)

    def resolve_path(self, rel_or_abs: str) -> Path:
        """将配置中的相对路径解析为相对项目根的绝对路径."""
        p = Path(rel_or_abs)
        if p.is_absolute():
            return p
        return (PROJECT_ROOT / p).resolve()


def _apply_env_overrides(cfg: dict[str, Any]) -> dict[str, Any]:
    """用环境变量覆盖关键配置项 (API Key / 模型名 / base_url)."""
    model = cfg.setdefault("model", {})
    api_key = os.getenv("DASHSCOPE_API_KEY")
    if api_key:
        model["api_key"] = api_key
    base_url = os.getenv("DASHSCOPE_BASE_URL")
    if base_url:
        model["base_url"] = base_url
    vision = os.getenv("QWEN_VISION_MODEL")
    if vision:
        model["vision_model"] = vision
    reasoning = os.getenv("QWEN_REASONING_MODEL")
    if reasoning:
        model["reasoning_model"] = reasoning
    return cfg


@lru_cache(maxsize=1)
def get_settings(config_path: str | None = None) -> Settings:
    """加载并缓存全局 Settings.

    优先级: 环境变量 > yaml 配置 > 默认值.
    """
    path = Path(config_path) if config_path else DEFAULT_CONFIG_PATH
    cfg: dict[str, Any] = {}
    if path.exists():
        with open(path, "r", encoding="utf-8") as f:
            cfg = yaml.safe_load(f) or {}
    cfg = _apply_env_overrides(cfg)

    model_cfg = cfg.get("model", {})
    pipe_cfg = cfg.get("pipeline", {})
    conc_cfg = cfg.get("concurrency", {})
    data_cfg = cfg.get("data", {})

    settings = Settings(
        project_name=cfg.get("project", {}).get("name", "table-agent"),
        model=ModelSettings(**{k: v for k, v in model_cfg.items() if k in ModelSettings.__dataclass_fields__}),
        pipeline=PipelineSettings(**{k: v for k, v in pipe_cfg.items() if k in PipelineSettings.__dataclass_fields__}),
        concurrency=ConcurrencySettings(**{k: v for k, v in conc_cfg.items() if k in ConcurrencySettings.__dataclass_fields__}),
        data=DataPaths(**{k: v for k, v in data_cfg.items() if k in DataPaths.__dataclass_fields__}),
        config_path=str(path),
    )
    return settings
