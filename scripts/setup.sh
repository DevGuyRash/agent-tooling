#!/usr/bin/env sh
set -eu

log() {
  printf '%s\n' "setup: $*" >&2
}

build_rust_skill() {
  name="$1"
  skip_flag_value="$2"
  skip_flag_name="$3"
  manifest_path="$4"
  action_prefix="$5"

  if [ "${skip_flag_value}" = "1" ]; then
    log "skipping ${name} prebuild (${skip_flag_name}=1)"
  else
    log "${action_prefix} ${name} binaries (locked, release)"
    cargo build --manifest-path "${manifest_path}" --locked --release
  fi
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

if ! command -v cargo >/dev/null 2>&1; then
  log "warning: cargo not available; skipping skill prebuilds"
  exit 0
fi

build_rust_skill \
  "mpcr" \
  "${AGENT_SKILLS_SKIP_MPCR_BUILD:-}" \
  "AGENT_SKILLS_SKIP_MPCR_BUILD" \
  "skills/code-review/scripts/mpcr-src/Cargo.toml" \
  "prebuilding"

build_rust_skill \
  "pca" \
  "${AGENT_SKILLS_SKIP_PCA_BUILD:-}" \
  "AGENT_SKILLS_SKIP_PCA_BUILD" \
  "skills/principal-architect-tooling/pca/Cargo.toml" \
  "prebuilding"

build_rust_skill \
  "piascs" \
  "${AGENT_SKILLS_SKIP_PIASCS_BUILD:-}" \
  "AGENT_SKILLS_SKIP_PIASCS_BUILD" \
  "skills/principal-architect-tooling/piascs/Cargo.toml" \
  "prebuilding"

log "done"
