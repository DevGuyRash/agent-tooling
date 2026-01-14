#!/usr/bin/env sh
set -eu

log() {
  printf '%s\n' "setup: $*" >&2
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

if [ "${AGENT_SKILLS_SKIP_RUST:-}" = "1" ]; then
  log "skipping Rust install (AGENT_SKILLS_SKIP_RUST=1)"
else
  if ! command -v cargo >/dev/null 2>&1; then
    log "cargo not found; installing Rust toolchain via rustup (stable)"
    if command -v rustup >/dev/null 2>&1; then
      : # rustup exists; continue below.
    elif command -v curl >/dev/null 2>&1; then
      curl -fsSL https://sh.rustup.rs | sh -s -- -y --profile minimal --default-toolchain stable
    elif command -v wget >/dev/null 2>&1; then
      wget -qO- https://sh.rustup.rs | sh -s -- -y --profile minimal --default-toolchain stable
    else
      log "error: need curl or wget to install rustup"
      exit 1
    fi

    # Re-export path for the current process after rustup install.
    if [ -d "${HOME}/.cargo/bin" ]; then
      case ":${PATH}:" in
        *":${HOME}/.cargo/bin:"*) : ;;
        *) PATH="${HOME}/.cargo/bin:${PATH}"; export PATH ;;
      esac
    fi
  fi

  if command -v rustup >/dev/null 2>&1; then
    rustup toolchain install stable \
      --component rustfmt \
      --component clippy \
      --profile minimal \
      --no-self-update
    rustup default stable >/dev/null 2>&1 || true
  fi
fi

# Ensure the default session root exists (gitignored).
mkdir -p .local/reports/code_reviews

if [ "${AGENT_SKILLS_SKIP_MPCR_BUILD:-}" = "1" ]; then
  log "skipping mpcr prebuild (AGENT_SKILLS_SKIP_MPCR_BUILD=1)"
  exit 0
fi

if ! command -v cargo >/dev/null 2>&1; then
  log "warning: cargo not available; skipping mpcr prebuild"
  exit 0
fi

log "prebuilding mpcr binaries (locked, release)"
cargo build --manifest-path skills/code-review/scripts/mpcr-src/Cargo.toml --locked --release

log "done"
