#!/usr/bin/env bash
#=============================================================================
#  Synchronize local repository changes to the remote GitHub repository.
#
#  This script performs a safe, ordered sync workflow:
#    1. Verify git availability and repository state
#    2. Check for initial commit (skip stash on fresh repos)
#    3. Stash any local uncommitted changes (optional)
#    4. Pull latest remote changes with rebase (optional)
#    5. Stage all changes with a generated or user-provided commit message
#    6. Detect unpushed commits (ahead count) regardless of working tree state
#    7. Push to remote, auto-setting upstream when the remote branch is new
#    8. Restore stashed changes (if any were saved)
#
#  Usage:
#    ./scripts/sync_to_github.sh                           # auto message, no pull
#    ./scripts/sync_to_github.sh "feat: add table parser"  # custom commit message
#    COMMIT_MSG="fix: bug in locator" ./scripts/sync_to_github.sh
#
#  Environment variables (optional configuration):
#    COMMIT_MSG    Override commit message (positional $1 has higher priority)
#    PULL_BEFORE   "1"  → pull --rebase before committing / pushing
#    AUTO_STASH    "1"  → stash before pull and restore afterwards
#    DRY_RUN       "1"  → print git commands without executing them
#    REMOTE_NAME   default "origin"
#    BRANCH_NAME   default: currently checked-out branch
#    GIT_CONFIG    Path to a sourced env file (REMOTE_URL, GIT_AUTHOR_NAME,
#                  GIT_AUTHOR_EMAIL, GITHUB_TOKEN) — avoids persisting tokens.
#=============================================================================
set -euo pipefail
IFS=$'\n\t'

# --- Script metadata ---------------------------------------------------------
readonly SCRIPT_NAME="$(basename "$0")"
readonly SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# --- Defaults (can be overridden by env vars or positional args) -------------
COMMIT_MSG="${1:-${COMMIT_MSG:-}}"
PULL_BEFORE="${PULL_BEFORE:-0}"
AUTO_STASH="${AUTO_STASH:-0}"
DRY_RUN="${DRY_RUN:-0}"
REMOTE_NAME="${REMOTE_NAME:-origin}"
BRANCH_NAME="${BRANCH_NAME:-}"
GIT_CONFIG="${GIT_CONFIG:-}"

STASH_NAME=""
STASH_CREATED=0

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

# --- Low-level git runner with dry-run support ------------------------------
run_git() {
    # Execute a git command, or echo it when DRY_RUN=1.
    # Returns the actual exit code (or 0 in dry-run).
    if [[ "$DRY_RUN" == "1" || "$DRY_RUN" == "true" ]]; then
        log_dim "[dry-run] git $*"
        return 0
    fi
    log_dim "[cmd] git $*"
    set +e
    git "$@"
    local rc=$?
    set -e
    return $rc
}

# --- Optional git-config env file sourcing -----------------------------------
load_git_config() {
    # Source optional GIT_CONFIG env file for secrets / author overrides.
    if [[ -z "$GIT_CONFIG" ]]; then
        return 0
    fi
    if [[ ! -f "$GIT_CONFIG" ]]; then
        log_warn "GIT_CONFIG=$GIT_CONFIG not found, skipping"
        return 0
    fi
    log_info "loading git config env file: $GIT_CONFIG"
    # shellcheck disable=SC1090
    source "$GIT_CONFIG"
}

# --- Preconditions -----------------------------------------------------------
ensure_git_available() {
    # Verify git command exists and report version.
    if ! command -v git >/dev/null 2>&1; then
        log_error "git not found in PATH. Please install Git and try again."
        exit 1
    fi
    local v
    v="$(git --version)"
    log_ok "$v"
}

ensure_inside_repo() {
    # Confirm CWD is inside a git repository.
    if ! git rev-parse --is-inside-work-tree >/dev/null 2>&1; then
        log_error "Not inside a git repository. Run 'git init' first."
        exit 1
    fi
}

# --- State helpers -----------------------------------------------------------
has_initial_commit() {
    # Return 0 if HEAD points to a commit (repository has at least one commit).
    git rev-parse --verify HEAD >/dev/null 2>&1
}

resolve_branch_name() {
    # Populate BRANCH_NAME with the current branch if unset.
    if [[ -z "$BRANCH_NAME" ]]; then
        BRANCH_NAME="$(git rev-parse --abbrev-ref HEAD 2>/dev/null || true)"
        if [[ -z "$BRANCH_NAME" || "$BRANCH_NAME" == "HEAD" ]]; then
            log_error "Detached HEAD or empty branch; set BRANCH_NAME explicitly."
            exit 1
        fi
    fi
    log_info "branch: ${BRANCH_NAME}"
}

remote_branch_exists() {
    # Return 0 if refs/remotes/<remote>/<branch> exists locally after fetch.
    local remote="$1"
    local branch="$2"
    git show-ref --verify --quiet "refs/remotes/${remote}/${branch}"
}

count_unpushed_commits() {
    # Echo the number of local commits ahead of the remote tracking ref.
    # If no tracking ref is configured, echo "NEW" to signal first push.
    local remote="$1"
    local branch="$2"
    if ! remote_branch_exists "$remote" "$branch"; then
        echo "NEW"
        return 0
    fi
    local upstream="${remote}/${branch}"
    local count
    count="$(git rev-list --count "${upstream}..${branch}" 2>/dev/null || echo "0")"
    echo "$count"
}

working_tree_dirty() {
    # Return 0 if there are uncommitted changes in the working tree or index.
    [[ -n "$(git status --porcelain 2>/dev/null)" ]]
}

generate_commit_message() {
    # Auto-generate a commit message with timestamp and changed-file summary.
    local stamp
    stamp="$(date '+%Y-%m-%d %H:%M:%S')"
    local summary
    summary="$(git diff --cached --name-status | awk 'NR<=5 {printf "%s ", $2} END {print ""}' | sed 's/ $//')"
    if [[ -z "$summary" ]]; then
        summary="$(git diff --name-status | awk 'NR<=5 {printf "%s ", $2} END {print ""}' | sed 's/ $//')"
    fi
    if [[ -z "$summary" ]]; then
        echo "chore: sync at ${stamp}"
    else
        echo "chore: sync at ${stamp} | ${summary}"
    fi
}

# --- Sync operations ---------------------------------------------------------
apply_stash() {
    # Stash working tree changes when AUTO_STASH enabled and repo has commits.
    if [[ "$AUTO_STASH" != "1" && "$AUTO_STASH" != "true" ]]; then
        return 0
    fi
    if ! has_initial_commit; then
        log_warn "no initial commit, skipping stash to avoid git error"
        return 0
    fi
    if ! working_tree_dirty; then
        log_info "working tree clean, no stash needed"
        return 0
    fi
    STASH_NAME="auto-sync-$(date '+%s')"
    log_info "stashing uncommitted changes (name=${STASH_NAME})"
    if ! run_git stash push -m "$STASH_NAME" -u; then
        log_warn "git stash failed, continuing without stash"
        STASH_NAME=""
        return 0
    fi
    STASH_CREATED=1
}

restore_stash() {
    # Pop stash if one was created earlier (best-effort, non-fatal).
    if [[ $STASH_CREATED -ne 1 || -z "$STASH_NAME" ]]; then
        return 0
    fi
    log_info "restoring stashed changes"
    if ! run_git stash pop; then
        log_warn "git stash pop failed; please run 'git stash list' and restore manually"
        return 1
    fi
    STASH_CREATED=0
    STASH_NAME=""
    return 0
}

pull_remote() {
    # Pull latest remote with --rebase when PULL_BEFORE enabled.
    if [[ "$PULL_BEFORE" != "1" && "$PULL_BEFORE" != "true" ]]; then
        return 0
    fi
    log_info "pulling latest from ${REMOTE_NAME}/${BRANCH_NAME} with rebase"
    if ! has_initial_commit; then
        log_warn "no initial commit, skipping pull"
        return 0
    fi
    if ! remote_branch_exists "$REMOTE_NAME" "$BRANCH_NAME"; then
        log_warn "remote branch ${REMOTE_NAME}/${BRANCH_NAME} does not exist yet, skipping pull"
        return 0
    fi
    if ! run_git pull --rebase "$REMOTE_NAME" "$BRANCH_NAME"; then
        log_error "git pull --rebase failed. Resolve conflicts and re-run the script."
        restore_stash || true
        exit 1
    fi
}

stage_and_commit() {
    # Stage all changes and create a commit if there is something to commit.
    # Return 0 when a commit was created OR nothing was dirty; non-zero on error.
    if working_tree_dirty; then
        log_info "staging all changes (git add -A)"
        run_git add -A
    fi

    # Nothing staged -> no new commit required.
    if git diff --cached --quiet 2>/dev/null; then
        log_info "no staged changes; skipping commit creation"
        return 0
    fi

    if [[ -z "$COMMIT_MSG" ]]; then
        COMMIT_MSG="$(generate_commit_message)"
        log_dim "using auto commit message: ${COMMIT_MSG}"
    else
        log_dim "using provided commit message: ${COMMIT_MSG}"
    fi

    if ! run_git commit -m "$COMMIT_MSG"; then
        log_error "git commit failed"
        restore_stash || true
        exit 1
    fi
    log_ok "commit created"
    return 0
}

ensure_remote() {
    # Verify REMOTE_NAME is configured; optionally update URL from REMOTE_URL.
    local remote_url
    if ! git remote get-url "$REMOTE_NAME" >/dev/null 2>&1; then
        log_error "remote '${REMOTE_NAME}' is not configured."
        log_info "Add it manually: git remote add ${REMOTE_NAME} <your-github-repo-url>"
        if [[ -n "${REMOTE_URL:-}" ]]; then
            log_info "REMOTE_URL detected, adding remote automatically"
            if ! run_git remote add "$REMOTE_NAME" "$REMOTE_URL"; then
                log_error "failed to add remote ${REMOTE_NAME}"
                exit 1
            fi
        else
            exit 1
        fi
    fi
    remote_url="$(git remote get-url "$REMOTE_NAME" 2>/dev/null || true)"
    log_info "remote: ${REMOTE_NAME} -> ${remote_url}"
}

push_to_remote() {
    # Push current branch; set upstream automatically on first push.
    # Skip push entirely when there are 0 unpushed commits.
    local ahead
    ahead="$(count_unpushed_commits "$REMOTE_NAME" "$BRANCH_NAME")"

    if [[ "$ahead" == "0" ]]; then
        log_ok "no unpushed commits; remote ${REMOTE_NAME}/${BRANCH_NAME} is already up to date"
        return 0
    fi

    if [[ "$ahead" == "NEW" ]]; then
        log_info "remote branch does not exist; first push with --set-upstream"
        if ! run_git push --set-upstream "$REMOTE_NAME" "$BRANCH_NAME"; then
            log_error "git push (first) failed"
            restore_stash || true
            exit 1
        fi
        log_ok "first push completed, upstream configured"
        return 0
    fi

    log_info "ahead by ${ahead} commit(s); pushing to ${REMOTE_NAME}/${BRANCH_NAME}"
    if ! run_git push "$REMOTE_NAME" "$BRANCH_NAME"; then
        log_error "git push failed"
        restore_stash || true
        exit 1
    fi
    log_ok "push completed"
}

# --- Entry point -------------------------------------------------------------
main() {
    # Main workflow: env checks → stash → pull → commit → push → unstash.
    local project_root
    project_root="$(get_project_root)"
    log_info "project root: ${project_root}"
    cd "${project_root}"

    load_git_config
    ensure_git_available
    ensure_inside_repo
    ensure_remote
    resolve_branch_name

    apply_stash
    pull_remote
    stage_and_commit
    push_to_remote
    restore_stash || true

    echo
    log_ok "local -> ${REMOTE_NAME}/${BRANCH_NAME} sync finished successfully"
}

main "$@"
