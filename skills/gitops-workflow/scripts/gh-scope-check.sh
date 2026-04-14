#!/usr/bin/env bash
# gitops-catalog: {"id":"governance-check","topic":"governance","command":"governance check","phrases":["governance check","gh scope check"],"summary":"Check GitHub governance capabilities before applying policy changes.","script":"gh-scope-check.sh","creates_branch":false,"creates_worktree":false,"creates_pr":false,"mutates_history":false,"stays_on_current_branch":true,"supports_json":true}
set -euo pipefail

# gh-scope-check.sh - Deterministic GitHub capability preflight for governance flows.
#
# Usage:
#   bash scripts/gh-scope-check.sh --repo owner/repo [--format text|json]
#
# Exit codes:
#   0  all capability probes passed
#   2  setup/argument error
#   5  permission/capability/network/api failure (fail-closed)

EXIT_SETUP=2
EXIT_PERMISSIONS=5

REPO=""
FORMAT="text"

die() {
  echo "Error: $1" >&2
  exit "${2:-1}"
}

require_cmd() {
  command -v "$1" >/dev/null 2>&1 || die "missing required command: $1" "$EXIT_PERMISSIONS"
}

require_opt_value() {
  local opt="$1"
  local val="${2:-}"
  if [[ -z "$val" || "$val" == --* ]]; then
    die "option '$opt' requires a value" "$EXIT_SETUP"
  fi
}

print_help() {
  cat <<'USAGE'
Usage:
  bash scripts/gh-scope-check.sh --repo owner/repo [--format text|json]

Options:
  --repo <owner/repo>  Target repository in owner/name form (required)
  --format <fmt>       Output format: text (default) or json
  -h, --help           Show this help text

Exit codes:
  0  all capability probes passed
  2  setup/argument error
  5  permission/capability/network/api failure
USAGE
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --repo)
      require_opt_value "--repo" "${2:-}"
      REPO="${2:-}"
      shift 2
      ;;
    --format)
      require_opt_value "--format" "${2:-}"
      FORMAT="${2:-}"
      shift 2
      ;;
    -h|--help)
      print_help
      exit 0
      ;;
    *)
      die "unknown argument: $1" "$EXIT_SETUP"
      ;;
  esac
done

[[ "$FORMAT" == "text" || "$FORMAT" == "json" ]] || die "invalid --format '$FORMAT' (expected: text or json)" "$EXIT_SETUP"
[[ -n "$REPO" ]] || die "--repo is required (expected owner/repo)" "$EXIT_SETUP"
[[ "$REPO" == */* ]] || die "--repo must be in owner/repo form" "$EXIT_SETUP"

require_cmd gh

normalize_reason() {
  local raw="${1:-}"
  local lowered
  lowered="$(echo "$raw" | tr '[:upper:]' '[:lower:]')"

  if [[ "$lowered" == *"resource not accessible by integration"* ]]; then
    echo "insufficient_token_permissions"
    return 0
  fi
  if [[ "$lowered" == *"requires"* && "$lowered" == *"scope"* ]]; then
    echo "insufficient_token_scopes"
    return 0
  fi
  if [[ "$lowered" == *"http 401"* || "$lowered" == *"http 403"* ]]; then
    echo "unauthorized_or_forbidden"
    return 0
  fi
  if [[ "$lowered" == *"http 404"* || "$lowered" == *"not found"* ]]; then
    echo "resource_not_found_or_no_access"
    return 0
  fi
  if [[ "$lowered" == *"could not resolve host"* || "$lowered" == *"timed out"* || "$lowered" == *"connection refused"* ]]; then
    echo "network_unavailable"
    return 0
  fi
  if [[ "$lowered" == *"not logged into"* || "$lowered" == *"authentication"* ]]; then
    echo "gh_not_authenticated"
    return 0
  fi

  echo "api_or_runtime_failure"
}

run_probe() {
  local check_name="$1"
  local path="$2"
  local out=""
  local code=0

  set +e
  out="$(gh api "$path" 2>&1)"
  code=$?
  set -e

  if [[ "$code" -eq 0 ]]; then
    PROBE_RESULTS+=("{\"name\":\"$check_name\",\"path\":\"$path\",\"status\":\"ok\"}")
    if [[ "$FORMAT" == "text" ]]; then
      echo "CHECK $check_name ... OK"
    fi
    return 0
  fi

  local reason
  reason="$(normalize_reason "$out")"
  PROBE_RESULTS+=("{\"name\":\"$check_name\",\"path\":\"$path\",\"status\":\"fail\",\"reason\":\"$reason\"}")
  FAILURE_CHECK="$check_name"
  FAILURE_REASON="$reason"
  FAILURE_DETAIL="$out"
  if [[ "$FORMAT" == "text" ]]; then
    echo "CHECK $check_name ... FAIL: $reason" >&2
  fi
  return 1
}

PROBE_RESULTS=()
FAILURE_CHECK=""
FAILURE_REASON=""
FAILURE_DETAIL=""

if ! run_probe "repo_metadata" "repos/$REPO"; then
  :
elif ! run_probe "rulesets_read" "repos/$REPO/rulesets"; then
  :
elif ! run_probe "labels_read" "repos/$REPO/labels?per_page=1&page=1"; then
  :
fi

if [[ -n "$FAILURE_CHECK" ]]; then
  if [[ "$FORMAT" == "json" ]]; then
    printf '{"status":"fail","repo":"%s","checks":[%s],"failure":{"check":"%s","reason":"%s","detail":"%s"}}\n' \
      "$REPO" \
      "$(IFS=,; echo "${PROBE_RESULTS[*]}")" \
      "$FAILURE_CHECK" \
      "$FAILURE_REASON" \
      "$(echo "$FAILURE_DETAIL" | head -n 1 | sed 's/"/\\"/g')"
  fi
  exit "$EXIT_PERMISSIONS"
fi

if [[ "$FORMAT" == "json" ]]; then
  printf '{"status":"ok","repo":"%s","checks":[%s]}\n' "$REPO" "$(IFS=,; echo "${PROBE_RESULTS[*]}")"
fi

exit 0
