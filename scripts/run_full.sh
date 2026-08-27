#!/usr/bin/env bash
#=============================================================================
#  Full run script: process ALL questions and produce the final submission.
#  Environment: Git Bash on Windows.
#
#  Configuration-driven (no argparse): all params come from configs/*.yaml +
#  optional env var overrides (CONFIG/OUTPUT/MAX_WORKERS/DPI/...).
#
#  Steps:
#    1. cd to project root
#    2. Set PYTHONPATH (.vendor only; src is resolvable via `python -m`)
#    3. Run `python -m src.main` with CONFIG=configs/default.yaml
#    4. Run preflight on the submission (CONFIG=configs/validate.yaml)
#
#  Usage:
#    ./scripts/run_full.sh
#    MAX_WORKERS=8 DPI=200 NO_INTERMEDIATE=1 ./scripts/run_full.sh
#    OUTPUT=data/output/final.xlsx ./scripts/run_full.sh
#=============================================================================
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"

# 默认走 default 场景 (全量运行); 用户可通过 CONFIG=... 切到其它 yaml.
export CONFIG="${CONFIG:-configs/default.yaml}"

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

# --- Warn on missing API key (still produces empty-answer submission) --------
[[ -n "${DASHSCOPE_API_KEY:-}" ]] || \
    echo "[WARN] DASHSCOPE_API_KEY env var not set. Will produce empty-answer submission." >&2

# --- Run pipeline (no CLI args; yaml + env vars drive everything) ------------
echo "[INFO] full pipeline (CONFIG=${CONFIG})..."
set +e
"$PY" -m src.main
pipeline_rc=$?
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
max_rc=$(( pipeline_rc > pf_rc ? pipeline_rc : pf_rc ))
if [[ $max_rc -eq 0 ]]; then
    echo "[ OK ] full run and preflight PASSED."
else
    echo "[WARN] full run finished with issues, review log above." >&2
fi
exit $max_rc
