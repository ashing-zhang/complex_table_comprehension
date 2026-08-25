#!/usr/bin/env bash
#=============================================================================
#  Full run script: process ALL questions and produce the final submission.
#
#  Configuration-driven (no argparse): all params come from configs/default.yaml
#  + optional env var overrides. This script:
#    1. Detects Python interpreter
#    2. cd to project root, sets PYTHONPATH (.vendor only)
#    3. Runs `python -m src.main` with CONFIG=configs/default.yaml
#    4. Runs preflight automatically on finish (CONFIG=configs/validate.yaml)
#    5. Propagates non-zero exit code
#
#  Usage:
#    ./scripts/run_full.sh
#    MAX_WORKERS=8 DPI=200 NO_INTERMEDIATE=1 ./scripts/run_full.sh
#    OUTPUT=data/output/final.xlsx ./scripts/run_full.sh
#=============================================================================
set -euo pipefail
IFS=$'\n\t'

# --- Script metadata ---------------------------------------------------------
readonly SCRIPT_NAME="$(basename "$0")"
readonly SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

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

# --- Second-precision time helpers -------------------------------------------
now_ts() {
    # Echo current epoch seconds (portable fallback to date).
    if command -v date >/dev/null 2>&1; then
        date +%s
    else
        echo 0
    fi
}

fmt_elapsed() {
    # Format a seconds delta to "HH:MM:SS".
    local secs="$1"
    local h=$(( secs / 3600 ))
    local m=$(( (secs % 3600) / 60 ))
    local s=$(( secs % 60 ))
    printf "%02d:%02d:%02d" "$h" "$m" "$s"
}

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
    # Full pipeline execution + timing + auto preflight.
    local project_root
    project_root="$(get_project_root)"
    log_info "project root: ${project_root}"
    cd "${project_root}"

    # Warn on missing API key (do not abort: still produces empty-answer submission).
    if [[ -z "${DASHSCOPE_API_KEY:-}" ]]; then
        log_warn "DASHSCOPE_API_KEY env var not set. Will produce empty-answer submission."
        log_warn "Please configure your Aliyun Bailian API key in .env and re-run for real answers."
    fi

    resolve_python

    local pp
    pp="$(build_pythonpath "${project_root}")"
    export PYTHONPATH="$pp"

    # 默认走 default 场景 (全量运行); 用户可通过 CONFIG=... 切到其它 yaml.
    export CONFIG="${CONFIG:-configs/default.yaml}"

    echo
    log_info "starting full pipeline (CONFIG=${CONFIG})..."
    log_dim "[cmd] ${PY_CMD[*]} -m src.main"
    echo

    local t_start t_end elapsed
    t_start="$(now_ts)"

    set +e
    "${PY_CMD[@]}" -m src.main
    local exit_code=$?
    set -e

    t_end="$(now_ts)"
    elapsed=$(( t_end - t_start ))
    log_info "elapsed: $(fmt_elapsed "$elapsed"), exit code: ${exit_code}"
    if [[ $exit_code -ne 0 ]]; then
        log_warn "pipeline returned non-zero exit code: ${exit_code}"
    fi

    # Auto preflight: 切到 validate 场景; 若用户覆写过 OUTPUT, 则顺带覆盖 SUBMISSION.
    local submission_target="${OUTPUT:-}"
    echo
    if [[ -n "$submission_target" ]]; then
        log_info "preflight checking submission: ${submission_target}"
    else
        log_info "preflight checking submission (from configs/validate.yaml)"
    fi
    set +e
    if [[ -n "$submission_target" ]]; then
        SUBMISSION="$submission_target" CONFIG=configs/validate.yaml "${PY_CMD[@]}" -m src.main
    else
        CONFIG=configs/validate.yaml "${PY_CMD[@]}" -m src.main
    fi
    local pf_exit_code=$?
    set -e

    local max_code
    max_code=$(( exit_code > pf_exit_code ? exit_code : pf_exit_code ))
    echo
    if [[ $max_code -eq 0 ]]; then
        log_ok "full run finished, submission preflight PASSED."
    else
        log_warn "Run finished with issues, please review the log output above."
    fi
    exit $max_code
}

main "$@"
