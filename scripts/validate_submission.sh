#!/usr/bin/env bash
#=============================================================================
#  Preflight check: validate an existing submission.xlsx via 8-step preflight.
#
#  Configuration-driven (no argparse): all params come from configs/validate.yaml
#  + optional env var overrides. This script:
#    1. Detects Python interpreter
#    2. cd to project root, sets PYTHONPATH (.vendor only)
#    3. Runs `python -m src.main` with CONFIG=configs/validate.yaml
#       (SUBMISSION env var can override the target file)
#
#  Invoked mode runs 8 preflight steps:
#    1. Column name correctness
#    2. Row count matches tests.xlsx
#    3. id set matches tests.xlsx
#    4. Unique ids (no duplicates)
#    5. Empty-answer ratio
#    6. structure / extract JSON validity
#    7. Thinking answers presence
#    8. Excel readability
#
#  Usage:
#    ./scripts/validate_submission.sh
#    ./scripts/validate_submission.sh data/output/my_submission.xlsx
#    SUBMISSION=data/output/other.xlsx ./scripts/validate_submission.sh
#=============================================================================
set -euo pipefail
IFS=$'\n\t'

# --- Script metadata ---------------------------------------------------------
readonly SCRIPT_NAME="$(basename "$0")"
readonly SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# --- Positional arg overrides SUBMISSION env var -----------------------------
# (保留位置参数兼容性; 不存在则回退到 validate.yaml 中的 submission 路径)
SUBMISSION_POS="${1:-}"
if [[ -n "$SUBMISSION_POS" ]]; then
    export SUBMISSION="$SUBMISSION_POS"
fi

# --- Color helpers -----------------------------------------------------------
_COLOR_OK=$'\033[32m'
_COLOR_WARN=$'\033[33m'
_COLOR_ERR=$'\033[31m'
_COLOR_INFO=$'\033[36m'
_COLOR_DIM=$'\033[90m'
_COLOR_RESET=$'\033[0m'

log_info()  { echo "${_COLOR_INFO}[INFO]${_COLOR_RESET}  $*" >&2; }
log_ok()    { echo "${_COLOR_OK}[ OK ]${_COLOR_RESET}  $*" >&2; }
log_warn()  { echo "${_COLOR_WARN}[WARN]${_COLOR_RESET}  $*" >&2; }
log_error() { echo "${_COLOR_ERR}[ERR ]${_COLOR_RESET}  $*" >&2; }
log_dim()   { echo "${_COLOR_DIM}$*${_COLOR_RESET}" >&2; }

# --- Project root ------------------------------------------------------------
get_project_root() {
    # Return absolute path of the project root directory.
    # shellcheck disable=SC2164
    (cd "${SCRIPT_DIR}/.." && pwd)
}

# --- Python interpreter detection -------------------------------------------
# Global array holding the resolved python command (may carry args like "py -3").
declare -a PY_CMD=()

resolve_python() {
    # Detect python via: python3 -> python -> py launcher -> abs paths.
    # Populates global PY_CMD array; exits script on failure.
    local candidates=(
        "python3"
        "python"
        "py -3"
    )
    local -a extra_candidates=(
        "/c/Python311/python.exe"
        "/c/Python310/python.exe"
        "/c/Python312/python.exe"
        "${LOCALAPPDATA:-}/Programs/Python/Python311/python.exe"
        "${LOCALAPPDATA:-}/Programs/Python/Python310/python.exe"
        "${LOCALAPPDATA:-}/Programs/Python/Python312/python.exe"
        "/Program Files/Python311/python.exe"
        "/Program Files/Python310/python.exe"
        "/Program Files/Python312/python.exe"
    )
    local cmd out

    for cmd in "${candidates[@]}"; do
        set +e
        out="$(bash -c "$cmd --version" 2>&1)"
        local rc=$?
        set -e
        if [[ $rc -eq 0 ]]; then
            log_ok "python found: $cmd ($out)"
            case "$cmd" in
                *' '*) IFS=' ' read -ra PY_CMD <<< "$cmd" ;;
                *) PY_CMD=("$cmd") ;;
            esac
            return 0
        fi
    done

    local path
    for path in "${extra_candidates[@]}"; do
        [[ -z "$path" ]] && continue
        if [[ -f "$path" ]]; then
            set +e
            out="$(bash -c "\"$path\" --version" 2>&1)"
            local rc=$?
            set -e
            if [[ $rc -eq 0 ]]; then
                log_ok "python found: $path ($out)"
                PY_CMD=("$path")
                return 0
            fi
        fi
    done

    log_error "Python 3.10+ not found. Please install Python and add it to PATH."
    exit 1
}

# --- PYTHONPATH builder ------------------------------------------------------
build_pythonpath() {
    # Assemble PYTHONPATH with only .vendor (vendored deps).
    # NOTE: <project_root>/src MUST NOT be added here — doing so shadows the
    # stdlib `io` package during interpreter startup (init_sys_streams),
    # causing "Fatal Python error: can't initialize sys standard streams".
    # `src` is resolvable as a top-level package because `python -m src.main`
    # prepends cwd (project root) to sys.path.
    local project_root="$1"
    local vendor_dir="${project_root}/.vendor"
    local result="${vendor_dir}"
    if [[ -n "${PYTHONPATH:-}" ]]; then
        result="${result}:${PYTHONPATH}"
    fi
    echo "$result"
}

# --- Entry point -------------------------------------------------------------
main() {
    # Preflight entry point: detect python -> set paths -> validate -> report.
    local project_root
    project_root="$(get_project_root)"
    log_info "project root: ${project_root}"
    cd "${project_root}"

    resolve_python

    local pp
    pp="$(build_pythonpath "${project_root}")"
    export PYTHONPATH="$pp"

    # 切到 validate 场景; 用户的位置参数 / SUBMISSION 环境变量会覆盖 yaml 中的 submission.
    export CONFIG="${CONFIG:-configs/validate.yaml}"

    echo
    if [[ -n "${SUBMISSION:-}" ]]; then
        log_info "preflight checking submission: ${SUBMISSION}"
    else
        log_info "preflight checking submission (from ${CONFIG})"
    fi
    echo

    set +e
    "${PY_CMD[@]}" -m src.main
    local code=$?
    set -e

    echo
    if [[ $code -eq 0 ]]; then
        log_ok "submission preflight PASSED."
    else
        log_error "preflight FAILED. Please fix the issues listed above and re-run."
    fi
    exit $code
}

main "$@"
