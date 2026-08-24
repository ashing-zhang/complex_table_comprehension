#!/usr/bin/env bash
#=============================================================================
#  Preflight check: validate an existing submission.xlsx via 8-step preflight.
#
#  Invokes src.main --validate-only, which checks:
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
#=============================================================================
set -euo pipefail
IFS=$'\n\t'

# --- Script metadata ---------------------------------------------------------
readonly SCRIPT_NAME="$(basename "$0")"
readonly SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# --- Defaults ----------------------------------------------------------------
SUBMISSION="${1:-${SUBMISSION:-data/output/submission.xlsx}}"
TESTS="${TESTS:-data/tests.xlsx}"

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

# --- Path existence guard ----------------------------------------------------
ensure_paths_exist() {
    # Abort if tests.xlsx or submission.xlsx missing.
    local tests="$1"
    local submission="$2"
    if [[ ! -f "$tests" ]]; then
        log_error "tests.xlsx not found: $tests"
        exit 1
    fi
    if [[ ! -f "$submission" ]]; then
        log_error "submission.xlsx not found: $submission"
        exit 1
    fi
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
    # Preflight entry point: env -> check paths -> validate -> report.
    local project_root
    project_root="$(get_project_root)"
    log_info "project root: ${project_root}"
    cd "${project_root}"

    resolve_python

    local pp
    pp="$(build_pythonpath "${project_root}")"
    export PYTHONPATH="$pp"

    ensure_paths_exist "$TESTS" "$SUBMISSION"

    local -a pf_args=(
        -m src.main
        --validate-only
        --tests "$TESTS"
        --submission "$SUBMISSION"
    )

    echo
    log_info "preflight checking submission: ${SUBMISSION}"
    echo

    set +e
    "${PY_CMD[@]}" "${pf_args[@]}"
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
