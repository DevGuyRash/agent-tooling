# Repo command surface for skill packaging, launcher validation, and local verification.
# Usage examples:
#   just bootstrap         # install packaging prerequisites used by repo scripts
#   just verify            # run the fast local verification surface
#   just ci                # run the pull-request verification surface for this repo
#   just dist-host         # build and stage host-platform skill binaries into dist/
#   just hooks-install     # install the local pre-commit gate
# project-harness: managed-file
set shell := ["bash", "-euo", "pipefail", "-c"]

# Show the available recipes and their descriptions
default:
  @just --list

# Install packaging prerequisites and prepare the workspace for local verification
bootstrap:
  python3 scripts/package_skills.py bootstrap

# Rewrite Rust source files into the canonical project style
fmt:
  cargo fmt --all

# Verify Rust formatting without rewriting source files
fmt-check:
  cargo fmt --all -- --check

# Run Clippy across the workspace and fail on warnings
lint:
  cargo clippy --workspace --all-targets --locked -- -D warnings

# Run the workspace test suite with the locked dependency graph
test:
  cargo test --workspace --locked

# Compile the Rust workspace in the default build profile
build:
  cargo build --workspace --locked

# Build and stage host-platform packaged binaries into skill dist/ directories
dist-host:
  python3 scripts/package_skills.py stage-host

# Run the fast local verification surface without packaging steps
verify: fmt-check lint test

# Render the Project Harness candidate files under .local/harness/render
harness-render:
  python3 skills/project-harness/scripts/project_harness.py render . --pretty

# Inspect the Project Harness view of this repo and local tool availability
harness-doctor:
  python3 skills/project-harness/scripts/project_harness.py doctor . --pretty

# Verify committed packaging policy and staged deliverables for the current host
verify-packaging:
  python3 scripts/package_skills.py verify-host

# Smoke-test skill-local launchers against the staged dist payloads
verify-skill-launchers:
  python3 scripts/package_skills.py smoke-launchers

# Run the pull-request verification surface, including packaging checks
ci: bootstrap verify
  @:
  just dist-host
  just verify-packaging
  just verify-skill-launchers

# Install a pre-commit hook that enforces the local verification surface
hooks-install:
  mkdir -p .git/hooks
  cat > .git/hooks/pre-commit <<'EOF'
  #!/usr/bin/env sh
  set -eu
  just verify
  just dist-host
  just verify-packaging
  EOF
  chmod +x .git/hooks/pre-commit
