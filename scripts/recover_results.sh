#!/usr/bin/env bash
#=============================================================================
#  Recover script: export journaled results (results.jsonl) to submission.xlsx.
#  Environment: Git Bash on Windows.
#
#  Configuration-driven (no argparse): all params come from configs/*.yaml +
#  optional env var overrides. This script:
#    1. cd to project root
#    2. Set PYTHONPATH (.vendor only; src is resolvable via `python -m`)
#    3. Run `RUN_MODE=recover python -m src.main` (reads data.journal,
#       writes data.output; missing ids filled with empty answers)
#    4. Run preflight on the recovered submission (CONFIG=configs/validate.yaml)
#
#  Usage:
#    ./scripts/recover_results.sh
#    JOURNAL=data/output/other.jsonl OUTPUT=data/output/recovered.xlsx ./scripts/recover_results.sh
#=============================================================================
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"

# 默认走 default 场景 (全量 recover); 用户可通过 CONFIG=... 切到其它 yaml.
export CONFIG="${CONFIG:-configs/default.yaml}"
# 强制 recover 模式: 仅从 JSONL 日志恢复, 不调用模型.
export RUN_MODE="recover"

cd "${PROJECT_ROOT}"

# --- Python (Git Bash: python -> python3 fallback) ---------------------------
PY=""
for c in python python3; do
    if command -v "$c" >/dev/null 2>&1 && "$c" --version >/dev/null 2>&1; then
        PY="$c"; break
    fi
done
[[ -n "$PY" ]] || { echo "[ERR] Python not found in PATH" >&2; exit 1; }

# --- PYTHONPATH: .vendor only (NOT src — would shadow stdlib `io`) ---------
VENDOR_DIR="${PROJECT_ROOT}/.vendor"
if [[ -n "${PYTHONPATH:-}" ]]; then
    export PYTHONPATH="${VENDOR_DIR}:${PYTHONPATH}"
else
    export PYTHONPATH="${VENDOR_DIR}"
fi

# --- Resolve journal path (for existence check) -----------------------------
# 优先级: JOURNAL 环境变量 > CONFIG 指向 yaml 的 data.journal > 默认值.
JOURNAL_TARGET="${JOURNAL:-}"
if [[ -z "$JOURNAL_TARGET" ]]; then
    # 从 yaml 读取 data.journal (容错: 无则回退默认值).
    JOURNAL_TARGET="$("$PY" -c "
import yaml, pathlib
p = pathlib.Path('${CONFIG}')
cfg = yaml.safe_load(p.read_text(encoding='utf-8')) if p.exists() else {}
print(cfg.get('data', {}).get('journal', 'data/output/results.jsonl'))
" 2>/dev/null || echo "data/output/results.jsonl")"
    JOURNAL_TARGET="${PROJECT_ROOT}/${JOURNAL_TARGET}"
fi

if [[ ! -f "$JOURNAL_TARGET" ]]; then
    echo "[ERR] journal not found: ${JOURNAL_TARGET}" >&2
    echo "[HINT] run ./scripts/run_full.sh first to produce it, or set JOURNAL=..." >&2
    exit 1
fi

# --- Recover: jsonl -> xlsx (no model calls) ---------------------------------
echo "[INFO] recover: ${JOURNAL_TARGET} -> submission.xlsx (CONFIG=${CONFIG})..."
set +e
"$PY" -m src.main
recover_rc=$?
set -e

# --- Preflight ---------------------------------------------------------------
# 切到 validate 场景; 若用户通过 OUTPUT 覆写过输出路径, 顺带覆盖 SUBMISSION.
SUBMISSION_TARGET="${OUTPUT:-}"
echo "[INFO] preflight: ${SUBMISSION_TARGET:-<configs/validate.yaml default>}"
set +e
if [[ -n "$SUBMISSION_TARGET" ]]; then
    SUBMISSION="$SUBMISSION_TARGET" CONFIG=configs/validate.yaml "$PY" -m src.main
else
    CONFIG=configs/validate.yaml "$PY" -m src.main
fi
pf_rc=$?
set -e

# --- Summary -----------------------------------------------------------------
max_rc=$(( recover_rc > pf_rc ? recover_rc : pf_rc ))
if [[ $max_rc -eq 0 ]]; then
    echo "[ OK ] recovery and preflight PASSED."
else
    echo "[WARN] recovery finished with issues, review log above." >&2
fi
exit $max_rc
