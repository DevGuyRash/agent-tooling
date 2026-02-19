#!/usr/bin/env bash
set -euo pipefail

# sensitive-scan.sh - Deterministic pre-commit sensitive data gate.
#
# Usage:
#   bash scripts/sensitive-scan.sh [--staged|--all] [--repo <path>] [--format text|json] [--redact] [--no-redact] [--no-download]
#
# Behavior:
# - Uses gitleaks to scan staged content (default) or full working tree.
# - Redacts finding values by default.
# - Attempts to keep scanner current by auto-resolving latest gitleaks release when possible.
# - Fails closed when no runnable scanner can be resolved.

EXIT_SETUP=2

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd -P)"
SKILL_ROOT="$(cd "$SCRIPT_DIR/.." && pwd -P)"

MODE="staged"
REPO_PATH="$(pwd -P)"
FORMAT="text"
REDACT="true"
ALLOW_DOWNLOAD="true"

# Optional overrides:
# - SENSITIVE_SCAN_GITLEAKS_VERSION: pin a specific version (for deterministic teams)
# - SENSITIVE_SCAN_BIN_DIR: alternate install location for managed binary
# - SENSITIVE_SCAN_CONFIG: alternate gitleaks config path
# - SENSITIVE_SCAN_DISABLE_UPDATE=1: skip latest-release lookup
# - SENSITIVE_SCAN_ALLOW_PATH_BIN=1: allow unverified PATH fallback (disabled by default)
GITLEAKS_VERSION_PIN="${SENSITIVE_SCAN_GITLEAKS_VERSION:-}"
BIN_DIR="${SENSITIVE_SCAN_BIN_DIR:-$SKILL_ROOT/.bin}"
CONFIG_PATH="${SENSITIVE_SCAN_CONFIG:-$SKILL_ROOT/assets/config/gitleaks.toml}"
DISABLE_UPDATE="${SENSITIVE_SCAN_DISABLE_UPDATE:-0}"
ALLOW_PATH_BIN="${SENSITIVE_SCAN_ALLOW_PATH_BIN:-0}"

LATEST_API_URL="https://api.github.com/repos/gitleaks/gitleaks/releases/latest"
GITLEAKS_BIN_NAME="gitleaks"

say() {
  echo "$*"
}

warn() {
  echo "Warning: $*" >&2
}

die() {
  echo "Error: $1" >&2
  exit "${2:-1}"
}

require_cmd() {
  command -v "$1" >/dev/null 2>&1 || die "missing required command: $1" "$EXIT_SETUP"
}

require_opt_value() {
  local opt="$1"
  local val="${2:-}"
  if [[ -z "$val" || "$val" == --* ]]; then
    die "option '$opt' requires a value" "$EXIT_SETUP"
  fi
}

allow_path_fallback() {
  case "${ALLOW_PATH_BIN,,}" in
    1|true|yes)
      return 0
      ;;
    *)
      return 1
      ;;
  esac
}

print_help() {
  cat <<'USAGE'
Usage:
  bash scripts/sensitive-scan.sh [--staged|--all] [--repo <path>] [--format text|json] [--redact] [--no-redact] [--no-download]

Options:
  --staged         Scan staged changes only (default).
  --all            Scan the entire working tree in --repo.
  --repo <path>    Repository path to scan (default: current directory).
  --format <fmt>   Output format: text (default) or json.
  --redact         Redact finding values in output (default).
  --no-redact      Disable redaction (not recommended).
  --no-download    Disable binary download/update behavior.
  -h, --help       Show this help text.

Exit codes:
  0  no findings
  1  findings detected
  2  setup/runtime error
USAGE
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --staged)
      MODE="staged"
      shift
      ;;
    --all)
      MODE="all"
      shift
      ;;
    --repo)
      require_opt_value "--repo" "${2:-}"
      REPO_PATH="${2:-}"
      shift 2
      ;;
    --format)
      require_opt_value "--format" "${2:-}"
      FORMAT="${2:-}"
      shift 2
      ;;
    --redact)
      REDACT="true"
      shift
      ;;
    --no-redact)
      REDACT="false"
      shift
      ;;
    --no-download)
      ALLOW_DOWNLOAD="false"
      shift
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
[[ -n "$REPO_PATH" ]] || die "--repo path is empty" "$EXIT_SETUP"
[[ -f "$CONFIG_PATH" ]] || die "missing scanner config: $CONFIG_PATH" "$EXIT_SETUP"

require_cmd git

if ! git -C "$REPO_PATH" rev-parse --is-inside-work-tree >/dev/null 2>&1; then
  die "--repo is not a git repository: $REPO_PATH" "$EXIT_SETUP"
fi

if [[ "$MODE" == "staged" ]]; then
  if [[ -z "$(git -C "$REPO_PATH" diff --cached --name-only)" ]]; then
    if [[ "$FORMAT" == "json" ]]; then
      printf '{"status":"skipped","mode":"staged","reason":"no_staged_changes"}\n'
    else
      say "No staged changes detected; skipping sensitive-data scan."
    fi
    exit 0
  fi
  if [[ -z "$(git -C "$REPO_PATH" diff --cached --name-only --diff-filter=d)" ]]; then
    if [[ "$FORMAT" == "json" ]]; then
      printf '{"status":"skipped","mode":"staged","reason":"deletions_only"}\n'
    else
      say "Only staged deletions detected; skipping sensitive-data scan."
    fi
    exit 0
  fi
fi

platform_asset_suffix() {
  local os arch
  os="$(uname -s | tr '[:upper:]' '[:lower:]')"
  arch="$(uname -m | tr '[:upper:]' '[:lower:]')"

  case "$os" in
    linux)
      case "$arch" in
        x86_64|amd64)
          echo "linux_x64"
          ;;
        aarch64|arm64)
          echo "linux_arm64"
          ;;
        *)
          return 1
          ;;
      esac
      ;;
    darwin)
      case "$arch" in
        x86_64|amd64)
          echo "darwin_x64"
          ;;
        arm64)
          echo "darwin_arm64"
          ;;
        *)
          return 1
          ;;
      esac
      ;;
    *)
      return 1
      ;;
  esac
}

extract_semver_tag() {
  local raw="$1"
  local parsed
  parsed="$(echo "$raw" | sed -nE 's/.*([0-9]+\.[0-9]+\.[0-9]+).*/v\1/p' | head -n 1)"
  echo "$parsed"
}

get_binary_version_tag() {
  local bin="$1"
  local out
  out="$("$bin" version 2>/dev/null || true)"
  extract_semver_tag "$out"
}

fetch_latest_version_tag() {
  if ! command -v curl >/dev/null 2>&1; then
    return 1
  fi
  local tag
  if command -v jq >/dev/null 2>&1; then
    tag="$(curl -fsSL "$LATEST_API_URL" | jq -r '.tag_name // empty' | head -n 1)"
  else
    tag="$(curl -fsSL "$LATEST_API_URL" | sed -nE 's/.*"tag_name"[[:space:]]*:[[:space:]]*"([^"]+)".*/\1/p' | head -n 1)"
  fi
  [[ -n "$tag" ]] || return 1
  echo "$tag"
}

sha256_file() {
  local f="$1"
  if command -v sha256sum >/dev/null 2>&1; then
    sha256sum "$f" | awk '{print $1}'
    return 0
  fi
  if command -v shasum >/dev/null 2>&1; then
    shasum -a 256 "$f" | awk '{print $1}'
    return 0
  fi
  return 1
}

install_version() {
  local tag="$1"
  local tag_no_v suffix asset base_url tmpdir archive checksums expected actual bin_source managed_hash

  tag_no_v="${tag#v}"
  suffix="$(platform_asset_suffix)" || die "unsupported platform for gitleaks auto-install ($(uname -s)/$(uname -m))" "$EXIT_SETUP"
  asset="gitleaks_${tag_no_v}_${suffix}.tar.gz"
  base_url="https://github.com/gitleaks/gitleaks/releases/download/${tag}"

  if ! command -v curl >/dev/null 2>&1; then
    return 1
  fi
  if ! command -v tar >/dev/null 2>&1; then
    return 1
  fi
  mkdir -p "$BIN_DIR"
  tmpdir="$(mktemp -d)"
  archive="$tmpdir/$asset"
  checksums="$tmpdir/gitleaks_checksums.txt"

  if ! curl -fsSL -o "$archive" "$base_url/$asset"; then
    rm -rf "$tmpdir"
    return 1
  fi
  if ! curl -fsSL -o "$checksums" "$base_url/gitleaks_${tag_no_v}_checksums.txt"; then
    rm -rf "$tmpdir"
    return 1
  fi

  expected="$(awk -v target="$asset" '$2 == target {print $1}' "$checksums")"
  if [[ -z "$expected" ]]; then
    rm -rf "$tmpdir"
    return 1
  fi

  if ! actual="$(sha256_file "$archive")"; then
    rm -rf "$tmpdir"
    return 1
  fi
  if [[ "$actual" != "$expected" ]]; then
    rm -rf "$tmpdir"
    die "download checksum mismatch for $asset" "$EXIT_SETUP"
  fi

  tar -xzf "$archive" -C "$tmpdir"
  bin_source="$(find "$tmpdir" -maxdepth 2 -type f -name "$GITLEAKS_BIN_NAME" | head -n 1)"
  if [[ -z "$bin_source" ]]; then
    rm -rf "$tmpdir"
    return 1
  fi

  cp "$bin_source" "$BIN_DIR/$GITLEAKS_BIN_NAME"
  chmod +x "$BIN_DIR/$GITLEAKS_BIN_NAME"
  if ! managed_hash="$(sha256_file "$BIN_DIR/$GITLEAKS_BIN_NAME")"; then
    rm -rf "$tmpdir"
    return 1
  fi
  printf '%s\n' "$managed_hash" > "$BIN_DIR/gitleaks.sha256"
  echo "$tag" > "$BIN_DIR/gitleaks.version"
  rm -rf "$tmpdir"

  echo "Installed gitleaks $tag at $BIN_DIR/$GITLEAKS_BIN_NAME" >&2
  echo "$BIN_DIR/$GITLEAKS_BIN_NAME"
}

is_trusted_managed_binary() {
  local bin="$1"
  local hash_file expected actual

  hash_file="$BIN_DIR/gitleaks.sha256"
  [[ -x "$bin" ]] || return 1
  [[ -f "$hash_file" ]] || return 1
  expected="$(head -n 1 "$hash_file" | tr -d '[:space:]')"
  [[ -n "$expected" ]] || return 1
  actual="$(sha256_file "$bin" 2>/dev/null || true)"
  [[ -n "$actual" ]] || return 1
  [[ "$actual" == "$expected" ]]
}

resolve_gitleaks_bin() {
  local explicit_bin local_bin path_bin desired_tag installed_tag path_tag fetched_tag

  explicit_bin="${GITLEAKS_BIN:-}"
  if [[ -n "$explicit_bin" ]]; then
    [[ -x "$explicit_bin" ]] || die "GITLEAKS_BIN is set but not executable: $explicit_bin" "$EXIT_SETUP"
    echo "$explicit_bin"
    return 0
  fi

  local_bin="$BIN_DIR/$GITLEAKS_BIN_NAME"
  path_bin=""
  if allow_path_fallback; then
    path_bin="$(command -v "$GITLEAKS_BIN_NAME" 2>/dev/null || true)"
  fi

  desired_tag="$GITLEAKS_VERSION_PIN"

  if [[ -z "$desired_tag" && "$DISABLE_UPDATE" != "1" && "$ALLOW_DOWNLOAD" == "true" ]]; then
    fetched_tag="$(fetch_latest_version_tag || true)"
    if [[ -n "$fetched_tag" ]]; then
      desired_tag="$fetched_tag"
    fi
  fi

  if [[ -n "$desired_tag" ]]; then
    if is_trusted_managed_binary "$local_bin"; then
      installed_tag="$(get_binary_version_tag "$local_bin")"
      if [[ "$installed_tag" == "$desired_tag" ]]; then
        echo "$local_bin"
        return 0
      fi
    fi

    if [[ -n "$path_bin" ]]; then
      path_tag="$(get_binary_version_tag "$path_bin")"
      if [[ "$path_tag" == "$desired_tag" ]]; then
        echo "$path_bin"
        return 0
      fi
    fi

    if [[ "$ALLOW_DOWNLOAD" == "true" ]]; then
      install_version "$desired_tag" && return 0
      if is_trusted_managed_binary "$local_bin"; then
        installed_tag="$(get_binary_version_tag "$local_bin")"
        if [[ "$installed_tag" == "$desired_tag" ]]; then
          echo "$local_bin"
          return 0
        fi
      fi
      if [[ -n "$path_bin" ]]; then
        path_tag="$(get_binary_version_tag "$path_bin")"
        if [[ "$path_tag" == "$desired_tag" ]]; then
          echo "$path_bin"
          return 0
        fi
      fi
      die "failed to install/update gitleaks $desired_tag and no fallback scanner is available" "$EXIT_SETUP"
    fi

    die "gitleaks version '$desired_tag' is required but no trusted scanner is available (download disabled)" "$EXIT_SETUP"
  fi

  if is_trusted_managed_binary "$local_bin"; then
    echo "$local_bin"
    return 0
  fi

  if [[ -n "$path_bin" ]]; then
    echo "$path_bin"
    return 0
  fi

  if [[ "$ALLOW_DOWNLOAD" == "true" ]]; then
    local fallback_tag
    fallback_tag="v8.30.0"
    install_version "$fallback_tag" && return 0
    die "unable to auto-install gitleaks and no scanner is available" "$EXIT_SETUP"
  fi

  die "gitleaks not found (set trusted GITLEAKS_BIN, allow path fallback with SENSITIVE_SCAN_ALLOW_PATH_BIN=1, or remove --no-download)" "$EXIT_SETUP"
}

GITLEAKS_BIN_PATH="$(resolve_gitleaks_bin)"

supports_subcommand() {
  local sub="$1"
  "$GITLEAKS_BIN_PATH" "$sub" --help >/dev/null 2>&1
}

SCAN_ARGS=()
if [[ "$MODE" == "staged" ]]; then
  if supports_subcommand protect; then
    SCAN_ARGS=(protect --staged --source . --config "$CONFIG_PATH" --exit-code 1 --no-banner)
  else
    SCAN_ARGS=(git --pre-commit --staged --config "$CONFIG_PATH" --exit-code 1 --no-banner)
  fi
else
  if supports_subcommand detect; then
    SCAN_ARGS=(detect --source . --config "$CONFIG_PATH" --exit-code 1 --no-banner)
  else
    SCAN_ARGS=(dir . --config "$CONFIG_PATH" --exit-code 1 --no-banner)
  fi
fi

if [[ "$REDACT" == "true" ]]; then
  SCAN_ARGS+=(--redact)
fi

if [[ "$FORMAT" == "json" ]]; then
  SCAN_ARGS+=(--report-format json --report-path /dev/stdout)
fi

set +e
(
  cd "$REPO_PATH"
  "$GITLEAKS_BIN_PATH" "${SCAN_ARGS[@]}"
)
SCAN_CODE=$?
set -e

if [[ "$SCAN_CODE" -eq 0 ]]; then
  if [[ "$FORMAT" == "json" ]]; then
    echo "Sensitive-data scan passed ($MODE)." >&2
  else
    say "Sensitive-data scan passed ($MODE)."
  fi
  exit 0
fi

if [[ "$SCAN_CODE" -eq 1 ]]; then
  echo "Sensitive-data scan found potential secrets/PII. Commit blocked." >&2
  exit 1
fi

echo "Sensitive-data scan failed due to scanner/runtime error (exit $SCAN_CODE)." >&2
exit "$EXIT_SETUP"
