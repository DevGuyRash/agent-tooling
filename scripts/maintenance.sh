#!/usr/bin/env sh
set -eu

script_dir="$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)"
repo_root="$(CDPATH= cd -- "${script_dir}/.." && pwd)"

# shellcheck source=scripts/common.sh
. "${script_dir}/common.sh"

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
  log "maintenance" "warning: cargo not available; run scripts/setup.sh to install Rust"
  exit 0
fi

compose_skip_flag="$(resolve_deprecated_flag \
  "maintenance" \
  "AGENT_TOOLING_SKIP_DOCKER_ARCHITECT_COMPOSE_BUILD" \
  "${AGENT_TOOLING_SKIP_DOCKER_ARCHITECT_COMPOSE_BUILD:-}" \
  "AGENT_SKILLS_SKIP_DOCKER_ARCHITECT_COMPOSE_BUILD" \
  "${AGENT_SKILLS_SKIP_DOCKER_ARCHITECT_COMPOSE_BUILD:-}")"

compose_skip_flag="$(resolve_deprecated_flag \
  "maintenance" \
  "AGENT_TOOLING_SKIP_DOCKER_ARCHITECT_COMPOSE_BUILD" \
  "${compose_skip_flag}" \
  "AGENT_SKILLS_SKIP_PCA_BUILD" \
  "${AGENT_SKILLS_SKIP_PCA_BUILD:-}")"

image_skip_flag="$(resolve_deprecated_flag \
  "maintenance" \
  "AGENT_TOOLING_SKIP_DOCKER_ARCHITECT_IMAGE_BUILD" \
  "${AGENT_TOOLING_SKIP_DOCKER_ARCHITECT_IMAGE_BUILD:-}" \
  "AGENT_SKILLS_SKIP_DOCKER_ARCHITECT_IMAGE_BUILD" \
  "${AGENT_SKILLS_SKIP_DOCKER_ARCHITECT_IMAGE_BUILD:-}")"

image_skip_flag="$(resolve_deprecated_flag \
  "maintenance" \
  "AGENT_TOOLING_SKIP_DOCKER_ARCHITECT_IMAGE_BUILD" \
  "${image_skip_flag}" \
  "AGENT_SKILLS_SKIP_PIASCS_BUILD" \
  "${AGENT_SKILLS_SKIP_PIASCS_BUILD:-}")"

mpcr_skip_flag="$(resolve_deprecated_flag \
  "maintenance" \
  "AGENT_TOOLING_SKIP_MPCR_BUILD" \
  "${AGENT_TOOLING_SKIP_MPCR_BUILD:-}" \
  "AGENT_SKILLS_SKIP_MPCR_BUILD" \
  "${AGENT_SKILLS_SKIP_MPCR_BUILD:-}")"

if [ "${mpcr_skip_flag}" = "1" ] && \
   [ "${compose_skip_flag}" = "1" ] && \
   [ "${image_skip_flag}" = "1" ]; then
  log "maintenance" "skipping host dist staging because all Rust skill build flags are disabled"
else
  log "maintenance" "bootstrapping Rust workspace dependencies"
  python3 scripts/package_skills.py bootstrap
  log "maintenance" "refreshing host packaged binaries into plugin-local skill dist/"
  python3 scripts/package_skills.py stage-host
fi

log "maintenance" "done"
