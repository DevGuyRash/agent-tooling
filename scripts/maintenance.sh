#!/usr/bin/env sh
set -eu

log() {
  printf '%s\n' "maintenance: $*" >&2
}

build_rust_skill() {
  name="$1"
  skip_var_name="$2"
  manifest_path="$3"
  action_prefix="$4"

  eval "skip_value=\${${skip_var_name}:-}"
  if [ "${skip_value}" = "1" ]; then
    log "skipping ${name} prebuild (${skip_var_name}=1)"
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

# Ensure the default session root exists (gitignored).
mkdir -p .local/reports/code_reviews

if ! command -v cargo >/dev/null 2>&1; then
  log "warning: cargo not available; run scripts/setup.sh to install Rust"
  exit 0
fi

build_rust_skill \
  "mpcr" \
  "AGENT_SKILLS_SKIP_MPCR_BUILD" \
  "skills/code-review/scripts/mpcr-src/Cargo.toml" \
  "updating/prebuilding"

if [ "${AGENT_SKILLS_SKIP_PCA_BUILD:-}" = "1" ] && [ "${AGENT_SKILLS_SKIP_PIASCS_BUILD:-}" = "1" ]; then
  log "skipping architecture skill prebuilds (AGENT_SKILLS_SKIP_PCA_BUILD=1 and AGENT_SKILLS_SKIP_PIASCS_BUILD=1)"
  exit 0
fi

build_rust_skill \
  "pca" \
  "AGENT_SKILLS_SKIP_PCA_BUILD" \
  "skills/principal-containerization-architect/scripts/pca-src/Cargo.toml" \
  "updating/prebuilding"

build_rust_skill \
  "piascs" \
  "AGENT_SKILLS_SKIP_PIASCS_BUILD" \
  "skills/principal-image-architecture-supply-chain-security-architect/scripts/piascs-src/Cargo.toml" \
  "updating/prebuilding"

log "done"
