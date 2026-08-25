#!/usr/bin/env bash
#=============================================================================
#  Small-scale debug script: run first N questions to sanity-check the pipeline.
#  Environment: Git Bash on Windows.
#
#  Steps:
#    1. cd to project root
#    2. Set PYTHONPATH (.vendor only; src is resolvable via `python -m`)
#    3. Run src.main --limit <LIMIT>
#    4. Run preflight on the generated submission
#
#  Usage:
#    ./scripts/debug_smoke.sh              # first 5 questions (default)
#    ./scripts/debug_smoke.sh 10           # first 10 questions
#    LIMIT=20 ./scripts/debug_smoke.sh     # env var override
#=============================================================================
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"

LIMIT="${1:-${LIMIT:-5}}"
TESTS="${TESTS:-data/tests.xlsx}"
FILES="${FILES:-data/files}"
OUTPUT="${OUTPUT:-data/output/submission_smoke.xlsx}"
NO_INTERMEDIATE="${NO_INTERMEDIATE:-0}"

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
[[ -f "$TESTS" ]] || { echo "[ERR] tests.xlsx not found: $TESTS" >&2; exit 1; }
[[ -d "$FILES" ]] || { echo "[ERR] table dir not found: $FILES" >&2; exit 1; }

# --- Build args -------------------------------------------------------------
args=(-m src.main --tests "$TESTS" --files "$FILES" --output "$OUTPUT" --limit "$LIMIT")
if [[ "$NO_INTERMEDIATE" == "1" || "$NO_INTERMEDIATE" == "true" ]]; then
    args+=(--no-intermediate)
fi

# --- Run pipeline -----------------------------------------------------------
echo "[INFO] smoke test (first ${LIMIT} questions)..."
set +e
"$PY" "${args[@]}"
pipeline_rc=$?
set -e

# --- Preflight ---------------------------------------------------------------
echo "[INFO] preflight: ${OUTPUT}"
set +e
"$PY" -m src.main --validate-only --tests "$TESTS" --submission "$OUTPUT"
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
