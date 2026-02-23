#!/usr/bin/env sh
# rust-development skill — Bootstrap scaffolding script.
#
# Usage:
#   scaffold.sh <workspace-root> [--clippy] [--banned-test] [--ci] [--all] [--force]
#
# Copies lint config, test harness, and/or CI workflow from the skill's
# assets/ directory into the target workspace.
#
# Options:
#   --clippy       Append workspace lint config to Cargo.toml
#   --banned-test  Copy banned_family.rs into a runnable crate test dir
#   --ci           Copy .github/workflows/ci.yml into the workspace
#   --all          All of the above
#   --force        Overwrite existing files
#
# The script is idempotent: it uses sentinel comments to detect prior runs
# and will not duplicate content.

set -eu

# ---------------------------------------------------------------------------
# Resolve skill root (where assets/ lives)
# ---------------------------------------------------------------------------
script_path="$0"
case "$script_path" in
  */*) : ;;
  *)
    resolved="$(command -v -- "$script_path" 2>/dev/null || true)"
    case "$resolved" in
      */*) script_path="$resolved" ;;
    esac
    ;;
esac

if command -v readlink >/dev/null 2>&1; then
  while [ -L "$script_path" ]; do
    link="$(readlink "$script_path" 2>/dev/null || true)"
    [ -n "$link" ] || break
    case "$link" in
      /*) script_path="$link" ;;
      *) script_path="$(dirname -- "$script_path")/$link" ;;
    esac
  done
fi

script_dir="$(CDPATH= cd -- "$(dirname -- "$script_path")" && pwd)"
skill_root="$(CDPATH= cd -- "$script_dir/.." && pwd)"
assets_dir="${skill_root}/assets"

CLIPPY_SENTINEL="# rust-development-skill:clippy-lints"

# ---------------------------------------------------------------------------
# Argument parsing
# ---------------------------------------------------------------------------
workspace_root=""
do_clippy=0
do_banned=0
do_ci=0
force=0

usage() {
  echo "Usage: scaffold.sh <workspace-root> [--clippy] [--banned-test] [--ci] [--all] [--force]"
  exit "${1:-2}"
}

if [ $# -eq 0 ]; then
  usage 2
fi

if [ "$1" = "-h" ] || [ "$1" = "--help" ]; then
  usage 0
fi

workspace_root="$1"
shift

while [ $# -gt 0 ]; do
  case "$1" in
    --clippy)      do_clippy=1 ;;
    --banned-test) do_banned=1 ;;
    --ci)          do_ci=1 ;;
    --all)         do_clippy=1; do_banned=1; do_ci=1 ;;
    --force)       force=1 ;;
    -h|--help)     usage 0 ;;
    *)
      echo "error: unknown option: $1" >&2
      usage 2
      ;;
  esac
  shift
done

if [ "$do_clippy" -eq 0 ] && [ "$do_banned" -eq 0 ] && [ "$do_ci" -eq 0 ]; then
  echo "error: specify at least one of --clippy, --banned-test, --ci, or --all" >&2
  usage 2
fi

if [ ! -d "$workspace_root" ]; then
  echo "error: workspace root does not exist: $workspace_root" >&2
  exit 1
fi

workspace_root="$(CDPATH= cd -- "$workspace_root" && pwd -P)"

if [ ! -f "$workspace_root/Cargo.toml" ]; then
  echo "error: workspace root must contain Cargo.toml: $workspace_root" >&2
  exit 1
fi

git_root=""
if command -v git >/dev/null 2>&1; then
  git_root="$(git -C "$workspace_root" rev-parse --show-toplevel 2>/dev/null || true)"
  if [ -n "$git_root" ]; then
    git_root="$(CDPATH= cd -- "$git_root" && pwd -P)"
    case "$workspace_root" in
      "$git_root"|"$git_root"/*) ;;
      *)
        echo "error: workspace root is outside repository root: $workspace_root" >&2
        echo "hint: expected a path under $git_root" >&2
        exit 1
        ;;
    esac
  fi
fi

if [ -z "$git_root" ] && ! grep -qF '[workspace]' "$workspace_root/Cargo.toml"; then
  echo "warning: Cargo.toml does not appear to be a workspace root (missing [workspace])" >&2
fi

ensure_within_workspace() {
  candidate="$1"
  case "$candidate" in
    "$workspace_root"|"$workspace_root"/*) ;;
    *)
      echo "  ✗ target escapes workspace root: $candidate" >&2
      return 1
      ;;
  esac

  parent_dir="$(dirname -- "$candidate")"
  mkdir -p "$parent_dir"
  parent_real="$(CDPATH= cd -- "$parent_dir" && pwd -P)"
  case "$parent_real" in
    "$workspace_root"|"$workspace_root"/*) ;;
    *)
      echo "  ✗ target parent resolves outside workspace root: $candidate" >&2
      return 1
      ;;
  esac
}

# ---------------------------------------------------------------------------
# Helper: safe copy (idempotent — skips if target exists and --force not set)
# ---------------------------------------------------------------------------
safe_copy() {
  src="$1"
  dst="$2"
  label="$3"

  if [ ! -f "$src" ]; then
    echo "  ✗ source not found: $src" >&2
    return 1
  fi

  if [ -L "$dst" ]; then
    echo "  ✗ refusing to overwrite symlink destination: $dst" >&2
    return 1
  fi

  ensure_within_workspace "$dst" || return 1
  if [ -d "$dst" ]; then
    echo "  ✗ refusing to overwrite directory destination: $dst" >&2
    return 1
  fi
  if [ -f "$dst" ] && [ "$force" -eq 0 ]; then
    echo "  ⚠ already exists (use --force to overwrite): $dst"
    return 0
  fi
  dst_parent="$(dirname -- "$dst")"
  parent_before="$(CDPATH= cd -- "$dst_parent" && pwd -P)"
  case "$parent_before" in
    "$workspace_root"|"$workspace_root"/*) ;;
    *)
      echo "  ✗ target parent resolves outside workspace root: $dst" >&2
      return 1
      ;;
  esac

  tmp_dst="$(mktemp "${dst_parent}/.scaffold-tmp.XXXXXX")"
  if ! cp -- "$src" "$tmp_dst"; then
    rm -f -- "$tmp_dst"
    return 1
  fi

  ensure_within_workspace "$dst" || {
    rm -f -- "$tmp_dst"
    return 1
  }
  if [ -L "$dst" ]; then
    rm -f -- "$tmp_dst"
    echo "  ✗ refusing to overwrite symlink destination: $dst" >&2
    return 1
  fi

  parent_after="$(CDPATH= cd -- "$dst_parent" && pwd -P)"
  if [ "$parent_before" != "$parent_after" ]; then
    rm -f -- "$tmp_dst"
    echo "  ✗ target parent changed during copy: $dst" >&2
    return 1
  fi

  # Re-check after copy in case the destination appeared between preflight and move.
  if [ -f "$dst" ] && [ "$force" -eq 0 ]; then
    rm -f -- "$tmp_dst"
    echo "  ⚠ already exists (use --force to overwrite): $dst"
    return 0
  fi
  if [ -d "$dst" ]; then
    rm -f -- "$tmp_dst"
    echo "  ✗ refusing to overwrite directory destination: $dst" >&2
    return 1
  fi

  mv -f -- "$tmp_dst" "$dst" || return 1
  if [ ! -f "$dst" ]; then
    echo "  ✗ destination missing after move: $dst" >&2
    return 1
  fi
  echo "  ✓ $label → $dst"
}

resolve_banned_test_destination() {
  root_manifest="${workspace_root}/Cargo.toml"
  default_dst="${workspace_root}/tests/banned_family.rs"

  if grep -Eq '^[[:space:]]*\[package\][[:space:]]*$' "$root_manifest"; then
    printf '%s\n' "$default_dst"
    return
  fi

  member_manifest="$(
    find "$workspace_root" -name Cargo.toml -print \
      | LC_ALL=C sort \
      | awk -v workspace_root="$workspace_root" -v root_manifest="$root_manifest" '
        $0 == root_manifest { next }
        {
          rel = $0
          prefix = workspace_root "/"
          if (index(rel, prefix) == 1) {
            rel = substr(rel, length(prefix) + 1)
          }
        }
        rel ~ /(^|\/)(\.git|\.github|target|node_modules|vendor|tests|test|testdata|fixtures|fixture|examples|benches)(\/|$)/ { next }
        { print; exit }
      '
  )"

  if [ -n "$member_manifest" ]; then
    printf '%s/tests/banned_family.rs\n' "$(dirname -- "$member_manifest")"
    return
  fi

  printf '%s\n' "$default_dst"
}

# ---------------------------------------------------------------------------
# Clippy lints — append with sentinel marker for idempotency
# ---------------------------------------------------------------------------
if [ "$do_clippy" -eq 1 ]; then
  echo "═══ Clippy lint config ═══"
  cargo_toml="${workspace_root}/Cargo.toml"
  clippy_src="${assets_dir}/clippy-lints.toml"

  if [ ! -f "$clippy_src" ]; then
    echo "  ✗ asset not found: $clippy_src" >&2
    exit 1
  fi

  if [ ! -f "$cargo_toml" ]; then
    echo "  ✗ Cargo.toml not found at: $cargo_toml" >&2
    exit 1
  fi
  if [ -L "$cargo_toml" ]; then
    echo "  ✗ refusing to edit symlinked Cargo.toml: $cargo_toml" >&2
    exit 1
  fi

  if grep -qF "$CLIPPY_SENTINEL" "$cargo_toml" 2>/dev/null; then
    if [ "$force" -eq 0 ]; then
      echo "  ⚠ clippy lints already present (sentinel found; use --force to replace)"
    else
      echo "  ⚠ --force: all content after sentinel will be replaced"
      # Remove old sentinel block and re-append
      # The sentinel marks the start; we remove everything from it to EOF
      # and re-append the fresh config.
      _tmp="$(mktemp "${TMPDIR:-/tmp}/rust-development-scaffold.XXXXXX")"
      if awk -v sentinel="$CLIPPY_SENTINEL" '
        $0 ~ sentinel { found=1 }
        !found
      ' "$cargo_toml" > "$_tmp" && mv "$_tmp" "$cargo_toml"; then
        :
      else
        rm -f "$_tmp"
        echo "  ✗ failed to rewrite Cargo.toml" >&2
        exit 1
      fi
      printf '\n%s\n' "$CLIPPY_SENTINEL" >> "$cargo_toml"
      cat "$clippy_src" >> "$cargo_toml"
      echo "  ✓ replaced clippy lint config in Cargo.toml"
    fi
  elif grep -q '\[workspace\.lints' "$cargo_toml" 2>/dev/null; then
    echo "  ⚠ [workspace.lints] already present (not from this skill). Review manually or use --force."
    if [ "$force" -eq 1 ]; then
      # Remove existing [workspace.lints*] sections before appending
      _tmp="$(mktemp "${TMPDIR:-/tmp}/rust-development-scaffold.XXXXXX")"
      if awk '
        /^\[workspace\.lints/ { skip=1; next }
        /^\[/                 { skip=0 }
        !skip
      ' "$cargo_toml" > "$_tmp" && mv "$_tmp" "$cargo_toml"; then
        :
      else
        rm -f "$_tmp"
        echo "  ✗ failed to rewrite Cargo.toml" >&2
        exit 1
      fi
      printf '\n%s\n' "$CLIPPY_SENTINEL" >> "$cargo_toml"
      cat "$clippy_src" >> "$cargo_toml"
      echo "  ✓ replaced existing [workspace.lints] with skill config"
    fi
  else
    printf '\n%s\n' "$CLIPPY_SENTINEL" >> "$cargo_toml"
    cat "$clippy_src" >> "$cargo_toml"
    echo "  ✓ appended clippy lint config to Cargo.toml"
  fi
  echo ""
fi

# ---------------------------------------------------------------------------
# Banned-family test
# ---------------------------------------------------------------------------
if [ "$do_banned" -eq 1 ]; then
  echo "═══ Banned-family test harness ═══"
  banned_dst="$(resolve_banned_test_destination)"
  if [ "$banned_dst" != "${workspace_root}/tests/banned_family.rs" ]; then
    echo "  ℹ virtual workspace detected; placing harness under: $(dirname -- "$banned_dst")"
  fi
  safe_copy \
    "${assets_dir}/banned_family.rs" \
    "$banned_dst" \
    "banned_family.rs"
  echo ""
fi

# ---------------------------------------------------------------------------
# CI workflow
# ---------------------------------------------------------------------------
if [ "$do_ci" -eq 1 ]; then
  echo "═══ GitHub Actions CI workflow ═══"
  safe_copy \
    "${assets_dir}/detect_rust_workspaces.py" \
    "${workspace_root}/.github/scripts/detect_rust_workspaces.py" \
    "detect_rust_workspaces.py"
  safe_copy \
    "${assets_dir}/ci.yml" \
    "${workspace_root}/.github/workflows/ci.yml" \
    "ci.yml"
  echo ""
fi

echo "Done."
