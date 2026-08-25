# 脚本目录

本目录提供 **Bash Shell 脚本**（`.sh`），覆盖项目常见操作。适用于：
- **Linux / macOS**：原生 Bash
- **Windows**：通过 **Git Bash**（推荐，安装 Git for Windows 自带）或 **WSL** 运行

## 配置驱动 (Configuration-Driven)

自 v2 起所有脚本采用 **YAML 配置 + 环境变量覆盖** 的解耦方式，**不再透传 CLI 参数到 `argparse`**：

- 主配置文件位于 [`configs/`](../configs/) 目录：
  | 文件 | 场景 | run.mode | run.limit | data.output |
  |---|---|---|---|---|
  | `configs/default.yaml` | 全量运行 | `run` | `0` (不限) | `data/output/submission.xlsx` |
  | `configs/smoke.yaml`   | 小规模调试 | `run` | `5` | `data/output/submission_smoke.xlsx` |
  | `configs/validate.yaml`| 提交前校验 | `validate` | `0` | `data/output/submission.xlsx` (run.submission) |
- 脚本通过 `CONFIG=configs/<scenario>.yaml` 环境变量切换场景。
- 一次性覆盖个别参数：直接在脚本前加环境变量（如 `LIMIT=20`），由 Python 侧的 `_apply_env_overrides()` 应用到 yaml 基础上。
- 直接调用 Python（不走脚本）也完全等价：
  ```bash
  python -m src.main                                    # 全量运行
  CONFIG=configs/smoke.yaml python -m src.main          # 小规模调试
  CONFIG=configs/validate.yaml python -m src.main       # 提交前校验
  LIMIT=20 OUTPUT=data/output/x.xlsx python -m src.main # 一次性覆盖
  ```

## 脚本清单

| 功能 | Shell 脚本 | 说明 |
|---|---|---|
| 小规模调试（前 N 题） | `debug_smoke.sh` | 默认 `CONFIG=configs/smoke.yaml`（前 5 题），跑完自动 preflight |
| 提交前检查（preflight） | `validate_submission.sh` | 默认 `CONFIG=configs/validate.yaml`，对已有 submission 做 8 步 preflight |
| 完整运行全量题目 | `run_full.sh` | 默认 `CONFIG=configs/default.yaml`，全量出分 + 计时 + 结束自动 preflight |
| 同步本地改动到 GitHub | `sync_to_github.sh` | 安全顺序：校验 → (可选 pull rebase) → 提交 → 推送到远程分支 |

## Windows 下如何执行 .sh 脚本

### 方式 A：Git Bash（强烈推荐）
安装 [Git for Windows](https://git-scm.com/download/win) 后，右键项目文件夹 → **Git Bash Here**，或在开始菜单打开 Git Bash，执行：

```bash
cd /c/AI/Competitions/complex_table_comprehension
bash scripts/debug_smoke.sh
```

### 方式 B：WSL（Windows Subsystem for Linux）
在 PowerShell 或 CMD 中：
```bash
wsl bash -c "cd /mnt/c/AI/Competitions/complex_table_comprehension && bash scripts/debug_smoke.sh"
```

## 使用前提

1. 在项目根目录复制 `.env.example` 为 `.env` 并填入 `DASHSCOPE_API_KEY`（阿里云百炼）。
2. 安装依赖：
   ```bash
   pip install -e .
   ```
   或最小依赖：
   ```bash
   pip install pandas openpyxl pillow numpy opencv-python openai pymupdf pydantic pyyaml
   ```

## 使用示例

### 1) 小规模调试

```bash
# 默认前 5 题 (CONFIG=configs/smoke.yaml, run.limit=5)
bash scripts/debug_smoke.sh

# 位置参数 (仍兼容): 前 10 题 (会设置 LIMIT=10 覆盖 yaml)
bash scripts/debug_smoke.sh 10

# 环境变量覆盖: 前 20 题 + 自定义输出路径
LIMIT=20 OUTPUT=data/output/my_smoke.xlsx bash scripts/debug_smoke.sh

# 切到自定义 yaml
CONFIG=configs/custom.yaml bash scripts/debug_smoke.sh
```

### 2) 提交前检查

```bash
# 检查 configs/validate.yaml 中的 submission (默认 data/output/submission.xlsx)
bash scripts/validate_submission.sh

# 位置参数 (仍兼容): 检查指定文件 (会设置 SUBMISSION=...)
bash scripts/validate_submission.sh data/output/my_submission.xlsx

# 环境变量覆盖
SUBMISSION=data/output/other.xlsx bash scripts/validate_submission.sh
```

### 3) 完整运行

```bash
# 全量运行 (CONFIG=configs/default.yaml)
bash scripts/run_full.sh

# 环境变量调参 (覆盖 yaml 默认)
MAX_WORKERS=8 DPI=200 NO_INTERMEDIATE=1 bash scripts/run_full.sh

# 覆盖输出路径
OUTPUT=data/output/final.xlsx bash scripts/run_full.sh
```

### 4) 同步本地改动到 GitHub

```bash
# 最简用法：自动生成提交信息，不执行 pull
bash scripts/sync_to_github.sh

# 自定义提交信息（位置参数）
bash scripts/sync_to_github.sh "feat: add multi-page table detector"

# 环境变量指定提交信息
COMMIT_MSG="fix: normalize answer whitespace" bash scripts/sync_to_github.sh

# 推送前先执行 pull --rebase（推荐在团队协作仓库使用），同时自动 stash/restore
PULL_BEFORE=1 AUTO_STASH=1 bash scripts/sync_to_github.sh

# 只预览将要执行的 git 命令（不实际执行，用于排查）
DRY_RUN=1 bash scripts/sync_to_github.sh

# 使用外部配置文件注入远程地址、作者、token（避免持久化到 remote URL）
#   示例配置文件内容：
#     REMOTE_URL=https://github.com/YourName/complex_table_comprehension.git
#     GIT_AUTHOR_NAME="Your Name"
#     GIT_AUTHOR_EMAIL="you@example.com"
#     GITHUB_TOKEN=ghp_xxx
GIT_CONFIG=./.git.env bash scripts/sync_to_github.sh

# 显式指定远程名 / 分支名（默认 origin 与当前分支）
REMOTE_NAME=origin BRANCH_NAME=main bash scripts/sync_to_github.sh
```

## 脚本自动做的事

- **Python 解释器探测回退链**（共 12 层，debug_smoke / run_full / validate）：
  `python3` → `python` → `py -3` → `C:\Python3xx\python.exe` → `%LOCALAPPDATA%\Programs\Python\Python3xx\python.exe` → `%ProgramFiles%\Python3xx\python.exe`
- 自动切换到项目根目录，避免 cwd 错误
- 自动设置 `PYTHONPATH = .vendor:$PYTHONPATH`（仅含 vendored 依赖；`src` 包通过 `python -m src.main` 由 cwd 解析，不加入 PYTHONPATH 以免遮蔽标准库 `io`）
- 严格模式：`set -euo pipefail` + `IFS=$'\n\t'`，出错立即终止并定位
- API Key 缺失告警（不终止，仍可生成空答案文件用于调试骨架流程）
- 前置路径检查：`tests.xlsx` / `files/` 存在性
- 后置 auto preflight：`debug_smoke.sh` 和 `run_full.sh` 跑完自动切换 `CONFIG=configs/validate.yaml` 触发 8 步 preflight
- **sync_to_github.sh 专有保护**：
  - 自动校验 git 可用性、是否在仓库内、remote 是否配置
  - 区分「工作区改动」和「未推送提交」两个独立条件，避免已提交但未推送时误判为「已是最新」
  - 无初始提交时跳过 stash / pull，避免 `You do not have the initial commit yet` 报错
  - 远端分支不存在时自动走首次 push 路径，不假设 `origin/<branch>` 必然存在
  - 支持 `DRY_RUN` 预览所有 git 命令，`AUTO_STASH` 自动暂存/还原未提交改动

## 所有可配置的环境变量

环境变量优先级高于 yaml 配置；未设置时使用 yaml 中的值。

| 变量名 | 适用脚本 | 覆盖目标 | 说明 |
|---|---|---|---|
| `CONFIG` | 全部 | yaml 文件选择 | 指向 `configs/<scenario>.yaml`，决定运行场景 |
| `RUN_MODE` | 全部 | `run.mode` | `run` / `validate`；通常由 yaml 决定，无需手设 |
| `LIMIT` | debug_smoke / run_full | `run.limit` | 处理前 N 道题（位置参数 `$1` 优先级更高，仅 debug_smoke） |
| `SUBMISSION` | validate_submission | `run.submission` | 待校验的 submission 路径（位置参数 `$1` 优先级更高） |
| `TESTS` | debug_smoke / run_full | `data.tests` | tests.xlsx 路径 |
| `FILES` | debug_smoke / run_full | `data.files` | 表格文件目录 |
| `OUTPUT` | debug_smoke / run_full | `data.output` | 输出 submission.xlsx 路径 |
| `MAX_WORKERS` | run_full | `concurrency.max_workers` | 最大并发 worker 数（>0 生效） |
| `DPI` | run_full | `pipeline.pdf_dpi` | PDF 渲染 DPI（>0 生效） |
| `NO_INTERMEDIATE` | debug_smoke / run_full | `pipeline.save_intermediate` | `1`/`true` 时不保存中间调试产物 |
| `DASHSCOPE_API_KEY` | run_full | `model.api_key` | 阿里云百炼 API Key，缺失会告警 |
| `DASHSCOPE_BASE_URL` | 全部 | `model.base_url` | OpenAI 兼容端点 |
| `QWEN_VISION_MODEL` | 全部 | `model.vision_model` | 视觉模型名 |
| `QWEN_REASONING_MODEL` | 全部 | `model.reasoning_model` | 推理模型名 |
| `COMMIT_MSG` | sync_to_github.sh | — | 提交信息（位置参数 `$1` 优先级更高） |
| `PULL_BEFORE` | sync_to_github.sh | — | `1` 时推送前执行 `git pull --rebase` |
| `AUTO_STASH` | sync_to_github.sh | — | `1` 时 pull 前自动 stash 并在推送后 restore |
| `DRY_RUN` | sync_to_github.sh | — | `1` 时仅打印 git 命令，不实际执行 |
| `REMOTE_NAME` | sync_to_github.sh | — | 远程仓库名 |
| `BRANCH_NAME` | sync_to_github.sh | — | 推送目标分支名 |
| `GIT_CONFIG` | sync_to_github.sh | — | 可选：含 `REMOTE_URL`/作者/`GITHUB_TOKEN` 的 env 文件路径 |

## 故障排查

### `python3: command not found` / `python: command not found`
- **Git Bash 用户**：在 Windows 安装 Python 时勾选 "Add Python to PATH"，并**重启 Git Bash** 让 PATH 生效。
- 或在脚本中直接补绝对路径：编辑 `resolve_python()` 中的 `extra_candidates` 数组。

### 路径中包含空格报错
脚本已默认对所有变量加双引号，若仍有问题请先确认：
- 是否用 `bash script.sh` 而非 `sh script.sh`（部分系统 sh ≠ bash）
- 是否按 `set -euo pipefail` 严格模式运行

### 想调试每条执行命令
在执行时加 `set -x` 即可：
```bash
bash -x scripts/debug_smoke.sh 10
```

### 想看 Python 侧实际生效的配置
脚本启动时会打印 `[INFO] config: <path> (mode=<run|validate>)`，可据此确认 yaml 是否切到期望场景。
