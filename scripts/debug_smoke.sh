#!/usr/bin/env bash
#=============================================================================
#  Small-scale debug script: run first N questions to sanity-check the pipeline.
#  Environment: Git Bash on Windows.
#
#  Configuration-driven (no argparse): all params come from configs/*.yaml +
#  optional env var overrides. This script selects the smoke scenario and
#  forwards user-supplied overrides (LIMIT/OUTPUT/MAX_WORKERS/DPI/...) to Python.
#
#  Steps:
#    1. cd to project root
#    2. Set PYTHONPATH (.vendor only; src is resolvable via `python -m`)
#    3. Run `python -m src.main` with CONFIG=configs/smoke.yaml
#    4. Run preflight on the generated submission (CONFIG=configs/validate.yaml)
#
#  Usage:
#    ./scripts/debug_smoke.sh              # first 5 questions (smoke.yaml default)
#    ./scripts/debug_smoke.sh 10           # first 10 questions (LIMIT override)
#    LIMIT=20 OUTPUT=data/output/x.xlsx ./scripts/debug_smoke.sh
#=============================================================================
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"

# 位置参数优先级 > 环境变量 > yaml 默认 (smoke.yaml: limit=5).
LIMIT_POS="${1:-}"
if [[ -n "$LIMIT_POS" ]]; then
    export LIMIT="$LIMIT_POS"
elif [[ -n "${LIMIT:-}" ]]; then
    export LIMIT
fi

# 默认走 smoke 场景; 用户可通过 CONFIG=... 切到其它 yaml.
export CONFIG="${CONFIG:-configs/smoke.yaml}"

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

# --- Input checks -----------------------------------------------------------
[[ -f "${TESTS:-data/tests.xlsx}" ]] || { echo "[ERR] tests.xlsx not found" >&2; exit 1; }
[[ -d "${FILES:-data/files}" ]] || { echo "[ERR] table dir not found" >&2; exit 1; }

# --- Run pipeline (no CLI args; yaml + env vars drive everything) ----------
echo "[INFO] smoke test (CONFIG=${CONFIG}, LIMIT=${LIMIT:-<yaml default>})..."
set +e
"$PY" -m src.main
pipeline_rc=$?
set -e

# --- Preflight ---------------------------------------------------------------
# 切到 validate 场景, 并通过 SUBMISSION 环境变量指向 smoke 输出文件.
# 若用户已通过 OUTPUT 覆盖 smoke 输出路径, 这里复用同一变量.
SMOKE_OUT="${OUTPUT:-data/output/submission_smoke.xlsx}"
echo "[INFO] preflight: ${SMOKE_OUT}"
set +e
SUBMISSION="$SMOKE_OUT" CONFIG=configs/validate.yaml "$PY" -m src.main
pf_rc=$?
set -e

# --- Summary -----------------------------------------------------------------
max_rc=$(( pipeline_rc > pf_rc ? pipeline_rc : pf_rc ))
if [[ $max_rc -eq 0 ]]; then
    echo "[ OK ] smoke test and preflight PASSED."
else
    echo "[WARN] smoke test finished with issues, review log above." >&2
fi
exit $max_rc
