"""全局配置加载与统一 Settings 工厂.

职责:
    1. 合并 configs/<scenario>.yaml 与环境变量, 形成统一的 Settings 对象.
    2. 所有模块均通过 get_settings() 获取配置, 避免散落的硬编码.
    3. 不使用 argparse; 运行场景由 CONFIG 环境变量指向不同的 yaml 文件决定,
       其余运行期参数 (limit / submission / max-workers / dpi / no-intermediate
       / tests / files / output) 全部以"环境变量 > yaml > 默认值"的优先级覆盖.

运行指南:
    - 默认全量运行:    python -m src.main
    - 小规模调试:      CONFIG=configs/smoke.yaml python -m src.main
    - 提交前校验:      CONFIG=configs/validate.yaml python -m src.main
    - 一次性覆盖示例:  LIMIT=20 OUTPUT=data/output/x.xlsx python -m src.main
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
# 选择 yaml 配置的环境变量名; 供 shell 脚本切换场景使用.
CONFIG_ENV_VAR = "CONFIG"

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
    use_llm_keywords: bool = True


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
class RunSettings:
    """运行模式与运行期参数.

    mode:        "run" 执行整批 pipeline; "validate" 仅做 submission preflight.
    limit:       仅处理前 N 道题, 0 或 None 表示不限.
    submission:  validate 模式下被校验的 submission 路径; 空字符串则回退到 data.output.
    """

    mode: str = "run"
    limit: int = 0
    submission: str = ""


@dataclass
class Settings:
    """统一配置对象."""

    project_name: str = "table-agent"
    model: ModelSettings = field(default_factory=ModelSettings)
    pipeline: PipelineSettings = field(default_factory=PipelineSettings)
    concurrency: ConcurrencySettings = field(default_factory=ConcurrencySettings)
    data: DataPaths = field(default_factory=DataPaths)
    run: RunSettings = field(default_factory=RunSettings)
    config_path: str = str(DEFAULT_CONFIG_PATH)

    def resolve_path(self, rel_or_abs: str) -> Path:
        """将配置中的相对路径解析为相对项目根的绝对路径."""
        p = Path(rel_or_abs)
        if p.is_absolute():
            return p
        return (PROJECT_ROOT / p).resolve()


def _to_int(value: Any) -> int | None:
    """容错将字符串/数字转 int, 非法返回 None."""
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _is_truthy(value: str | None) -> bool:
    """判定环境变量字符串是否为真值 (1/true, 大小写不敏感)."""
    return bool(value) and value.strip().lower() in ("1", "true", "yes", "on")


def _apply_env_overrides(cfg: dict[str, Any]) -> dict[str, Any]:
    """用环境变量覆盖关键配置项.

    覆盖范围 (均为可选, 未设置则保留 yaml 值):
        模型:     DASHSCOPE_API_KEY / DASHSCOPE_BASE_URL / QWEN_VISION_MODEL / QWEN_REASONING_MODEL
        运行期:   RUN_MODE / LIMIT / SUBMISSION / NO_INTERMEDIATE
        数据路径: TESTS / FILES / OUTPUT
        调参:     MAX_WORKERS / DPI
    """
    # --- 模型相关 ---
    model = cfg.setdefault("model", {})
    if api_key := os.getenv("DASHSCOPE_API_KEY"):
        model["api_key"] = api_key
    if base_url := os.getenv("DASHSCOPE_BASE_URL"):
        model["base_url"] = base_url
    if vision := os.getenv("QWEN_VISION_MODEL"):
        model["vision_model"] = vision
    if reasoning := os.getenv("QWEN_REASONING_MODEL"):
        model["reasoning_model"] = reasoning

    # --- 运行模式 / 运行期参数 ---
    run = cfg.setdefault("run", {})
    if mode := os.getenv("RUN_MODE"):
        run["mode"] = mode
    if (limit := _to_int(os.getenv("LIMIT"))) is not None:
        run["limit"] = limit
    if submission := os.getenv("SUBMISSION"):
        run["submission"] = submission

    # --- 数据路径 ---
    data = cfg.setdefault("data", {})
    if tests := os.getenv("TESTS"):
        data["tests"] = tests
    if files := os.getenv("FILES"):
        data["files"] = files
    if output := os.getenv("OUTPUT"):
        data["output"] = output

    # --- pipeline / 并发调参 ---
    pipe = cfg.setdefault("pipeline", {})
    if (dpi := _to_int(os.getenv("DPI"))) is not None and dpi > 0:
        pipe["pdf_dpi"] = dpi
    if _is_truthy(os.getenv("NO_INTERMEDIATE")):
        pipe["save_intermediate"] = False

    conc = cfg.setdefault("concurrency", {})
    if (mw := _to_int(os.getenv("MAX_WORKERS"))) is not None and mw > 0:
        conc["max_workers"] = mw

    return cfg


@lru_cache(maxsize=1)
def get_settings(config_path: str | None = None) -> Settings:
    """加载并缓存全局 Settings.

    配置文件解析顺序 (后者覆盖前者):
        1. dataclass 默认值
        2. yaml 配置文件
        3. 环境变量 (含 .env)

    config_path 显式参数 > CONFIG 环境变量 > configs/default.yaml.
    由于使用 lru_cache, 同一进程内首次调用即固化配置; 如需切换场景请在
    首次调用前设置 CONFIG 环境变量, 或通过 tests 中的 importlib.reload 切换.
    """
    # 显式参数 > 环境变量 > 默认.
    resolved = config_path or os.getenv(CONFIG_ENV_VAR) or str(DEFAULT_CONFIG_PATH)
    path = Path(resolved)
    cfg: dict[str, Any] = {}
    if path.exists():
        with open(path, "r", encoding="utf-8") as f:
            cfg = yaml.safe_load(f) or {}
    cfg = _apply_env_overrides(cfg)

    model_cfg = cfg.get("model", {})
    pipe_cfg = cfg.get("pipeline", {})
    conc_cfg = cfg.get("concurrency", {})
    data_cfg = cfg.get("data", {})
    run_cfg = cfg.get("run", {})

    settings = Settings(
        project_name=cfg.get("project", {}).get("name", "table-agent"),
        model=ModelSettings(**{k: v for k, v in model_cfg.items() if k in ModelSettings.__dataclass_fields__}),
        pipeline=PipelineSettings(**{k: v for k, v in pipe_cfg.items() if k in PipelineSettings.__dataclass_fields__}),
        concurrency=ConcurrencySettings(**{k: v for k, v in conc_cfg.items() if k in ConcurrencySettings.__dataclass_fields__}),
        data=DataPaths(**{k: v for k, v in data_cfg.items() if k in DataPaths.__dataclass_fields__}),
        run=RunSettings(**{k: v for k, v in run_cfg.items() if k in RunSettings.__dataclass_fields__}),
        config_path=str(path),
    )
    return settings
