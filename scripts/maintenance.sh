#!/usr/bin/env sh
set -eu

log() {
  printf '%s\n' "maintenance: $*" >&2
}

script_dir="$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)"
repo_root="$(CDPATH= cd -- "${script_dir}/.." && pwd)"

# Prefer git's idea of the repo root when available (handles symlinks / odd invocations).
if command -v git >/dev/null 2>&1; then
  git_root="$(git -C "$repo_root" rev-parse --show-toplevel 2>/dev/null || true)"
  if [ -n "${git_root}" ]; then
    repo_root="${git_root}"
  fi
fi

cd "$repo_root"

# Ensure cargo is discoverable when rustup installed in non-login shells.
if [ -d "${HOME}/.cargo/bin" ]; then
  case ":${PATH}:" in
    *":${HOME}/.cargo/bin:"*) : ;;
    *) PATH="${HOME}/.cargo/bin:${PATH}"; export PATH ;;
  esac
fi

# Avoid git safety issues in containerized environments (best-effort).
if command -v git >/dev/null 2>&1; then
  if ! git config --global --get-all safe.directory 2>/dev/null | grep -Fxq "$repo_root"; then
    git config --global --add safe.directory "$repo_root" 2>/dev/null || true
  fi
fi

# Ensure the default session root exists (gitignored).
mkdir -p .local/reports/code_reviews

if [ "${AGENT_SKILLS_SKIP_MPCR_BUILD:-}" = "1" ]; then
  log "skipping mpcr prebuild (AGENT_SKILLS_SKIP_MPCR_BUILD=1)"
  exit 0
fi

if ! command -v cargo >/dev/null 2>&1; then
  log "warning: cargo not available; run scripts/setup.sh to install Rust"
  exit 0
fi

log "updating/prebuilding mpcr binaries (locked, release)"
cargo build --manifest-path skills/code-review/scripts/mpcr-src/Cargo.toml --locked --release

log "done"
