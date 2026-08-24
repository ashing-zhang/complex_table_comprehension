# 脚本目录

本目录提供 **Bash Shell 脚本**（`.sh`），覆盖项目常见操作。适用于：
- **Linux / macOS**：原生 Bash
- **Windows**：通过 **Git Bash**（推荐，安装 Git for Windows 自带）或 **WSL** 运行

## 脚本清单

| 功能 | Shell 脚本 | 说明 |
|---|---|---|
| 小规模调试（前 N 题） | `debug_smoke.sh` | 默认跑前 5 题，跑完自动做 preflight 检查 |
| 提交前检查（preflight） | `validate_submission.sh` | 对已有 submission.xlsx 做 8 步 preflight |
| 完整运行全量题目 | `run_full.sh` | 正式全量出分 + 计时 + 结束自动 preflight |

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

所有脚本支持**位置参数**和**环境变量覆写**两种用法。

### 1) 小规模调试

```bash
# 默认前 5 题
bash scripts/debug_smoke.sh

# 位置参数：前 10 题
bash scripts/debug_smoke.sh 10

# 环境变量覆写：前 20 题 + 自定义输出路径
LIMIT=20 OUTPUT=data/output/my_smoke.xlsx bash scripts/debug_smoke.sh
```

### 2) 提交前检查

```bash
# 检查默认路径 data/output/submission.xlsx
bash scripts/validate_submission.sh

# 位置参数：检查指定文件
bash scripts/validate_submission.sh data/output/my_submission.xlsx

# 环境变量覆写
SUBMISSION=data/output/other.xlsx TESTS=data/tests.xlsx bash scripts/validate_submission.sh
```

### 3) 完整运行

```bash
# 全量运行默认配置
bash scripts/run_full.sh

# 环境变量调参（并发数、DPI、不存中间产物）
MAX_WORKERS=8 DPI=200 NO_INTERMEDIATE=1 bash scripts/run_full.sh

# 覆盖输入输出路径
TESTS=data/tests.xlsx FILES=data/files OUTPUT=data/output/final.xlsx bash scripts/run_full.sh
```

## 脚本自动做的事

- **Python 解释器探测回退链**（共 12 层）：
  `python3` → `python` → `py -3` → `C:\Python3xx\python.exe` → `%LOCALAPPDATA%\Programs\Python\Python3xx\python.exe` → `%ProgramFiles%\Python3xx\python.exe`
- 自动切换到项目根目录，避免 cwd 错误
- 自动设置 `PYTHONPATH = src:.vendor:$PYTHONPATH`，确保本地模块可被导入
- 严格模式：`set -euo pipefail` + `IFS=$'\n\t'`，出错立即终止并定位
- API Key 缺失告警（不终止，仍可生成空答案文件用于调试骨架流程）
- 前置路径检查：`tests.xlsx` / `files/` / `submission.xlsx` 存在性
- 后置 auto preflight：`debug_smoke.sh` 和 `run_full.sh` 跑完自动触发 8 步 preflight

## 所有可配置的环境变量

| 变量名 | 默认值 | 适用脚本 | 说明 |
|---|---|---|---|
| `LIMIT` | `5` | debug_smoke.sh | 处理前 N 道题（位置参数 `$1` 优先级更高） |
| `TESTS` | `data/tests.xlsx` | 全部 | tests.xlsx 路径 |
| `FILES` | `data/files` | debug_smoke / run_full | 表格文件目录 |
| `OUTPUT` | 见下 | debug_smoke / run_full | 输出 submission.xlsx 路径 |
| `SUBMISSION` | `data/output/submission.xlsx` | validate_submission.sh | 待检查的 submission 路径（`$1` 优先级更高） |
| `MAX_WORKERS` | `0`（使用项目默认） | run_full.sh | 最大并发 worker 数 |
| `DPI` | `0`（使用项目默认） | run_full.sh | PDF 渲染 DPI |
| `NO_INTERMEDIATE` | `0` | debug_smoke / run_full | `1` 或 `true` 时不保存中间调试产物 |
| `DASHSCOPE_API_KEY` | 空 | run_full.sh | 阿里云百炼 API Key，缺失会告警 |

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
