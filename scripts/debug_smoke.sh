#!/usr/bin/env bash
#=============================================================================
#  Small-scale debug script: run first N questions to sanity-check the pipeline.
#
#  Steps:
#    1. Detect Python interpreter (python3 -> python -> py launcher -> common abs paths)
#    2. Change to project root
#    3. Set PYTHONPATH (.vendor only; src is resolvable via `python -m`)
#    4. Invoke src.main --limit <LIMIT>
#    5. Run preflight on the generated submission automatically
#
#  Usage:
#    ./scripts/debug_smoke.sh              # first 5 questions (default)
#    ./scripts/debug_smoke.sh 10           # first 10 questions
#    LIMIT=20 ./scripts/debug_smoke.sh     # env var override
#=============================================================================
set -euo pipefail
IFS=$'\n\t'

# --- Script metadata ---------------------------------------------------------
readonly SCRIPT_NAME="$(basename "$0")"
readonly SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# --- Defaults (can be overridden by env vars or positional args) -------------
LIMIT="${1:-${LIMIT:-5}}"
TESTS="${TESTS:-data/tests.xlsx}"
FILES="${FILES:-data/files}"
OUTPUT="${OUTPUT:-data/output/submission_smoke.xlsx}"
NO_INTERMEDIATE="${NO_INTERMEDIATE:-0}"

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

# --- Determine the absolute project root (parent of scripts/) ----------------
get_project_root() {
    # Return absolute path of the project root directory.
    # shellcheck disable=SC2164
    (cd "${SCRIPT_DIR}/.." && pwd)
}

# --- Detect Python interpreter -----------------------------------------------
# Global array holding the resolved python command (may carry args like "py -3").
declare -a PY_CMD=()

resolve_python() {
    # Detect python via candidates in order: python3 -> python -> py -> abs paths.
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

    # Step 1: PATH-based candidates.
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

    # Step 2: Absolute-path candidates (relevant for Windows + Git Bash).
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

    log_error "Python 3.10+ not found. Please install Python and add it to PATH,"
    log_error "or edit this script with the absolute path."
    exit 1
}

# --- Preflight path checks ---------------------------------------------------
ensure_paths_exist() {
    # Verify required input paths exist; abort on missing.
    local tests="$1"
    local files="$2"
    if [[ ! -f "$tests" ]]; then
        log_error "tests.xlsx not found: $tests"
        exit 1
    fi
    if [[ ! -d "$files" ]]; then
        log_error "table dir not found: $files"
        exit 1
    fi
}

# --- Assemble PYTHONPATH -----------------------------------------------------
build_pythonpath() {
    # Assemble PYTHONPATH with only .vendor (vendored deps).
    # NOTE: <project_root>/src MUST NOT be added here — doing so shadows the
    # stdlib `io` package during interpreter startup (init_sys_streams),
    # causing "Fatal Python error: can't initialize sys standard streams".
    # The `src` package is resolvable as a top-level package because
    # `python -m src.main` prepends cwd (project root) to sys.path.
    local project_root="$1"
    local vendor_dir="${project_root}/.vendor"
    local sep=":"
    # Git Bash on Windows still uses ':' inside PYTHONPATH (CPython handles it).
    local result="${vendor_dir}"
    if [[ -n "${PYTHONPATH:-}" ]]; then
        result="${result}${sep}${PYTHONPATH}"
    fi
    echo "$result"
}

# --- Entry point -------------------------------------------------------------
main() {
    # Main workflow: env checks -> run pipeline -> preflight.
    local project_root
    project_root="$(get_project_root)"
    log_info "project root: ${project_root}"
    cd "${project_root}"

    resolve_python

    local pp
    pp="$(build_pythonpath "${project_root}")"
    export PYTHONPATH="$pp"
    log_dim "[env] PYTHONPATH=${PYTHONPATH}"

    ensure_paths_exist "$TESTS" "$FILES"

    # Build argument array.
    local -a args_list=(
        -m src.main
        --tests "$TESTS"
        --files "$FILES"
        --output "$OUTPUT"
        --limit "$LIMIT"
    )
    if [[ "$NO_INTERMEDIATE" == "1" || "$NO_INTERMEDIATE" == "true" ]]; then
        args_list+=(--no-intermediate)
    fi

    echo
    log_info "smoke test (first ${LIMIT} questions)..."
    log_dim "[cmd] ${PY_CMD[*]} ${args_list[*]}"
    echo

    set +e
    "${PY_CMD[@]}" "${args_list[@]}"
    local exit_code=$?
    set -e
    if [[ $exit_code -ne 0 ]]; then
        log_warn "pipeline returned non-zero exit code: ${exit_code}"
    fi

    # Auto preflight.
    echo
    log_info "preflight checking submission: ${OUTPUT}"
    local -a pf_args=(
        -m src.main
        --validate-only
        --tests "$TESTS"
        --submission "$OUTPUT"
    )
    set +e
    "${PY_CMD[@]}" "${pf_args[@]}"
    local pf_exit_code=$?
    set -e

    local max_code
    max_code=$(( exit_code > pf_exit_code ? exit_code : pf_exit_code ))
    if [[ $max_code -eq 0 ]]; then
        echo
        log_ok "smoke test finished and preflight PASSED."
    else
        echo
        log_warn "Smoke test finished with issues, please review the log output above."
    fi
    exit $max_code
}

main "$@"
