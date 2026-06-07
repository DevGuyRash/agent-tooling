# Repo command surface for skill packaging, launcher validation, and local verification.
# Usage examples:
#   just bootstrap         # install packaging prerequisites used by repo scripts
#   just verify            # run the fast local verification surface
#   just ci                # run the pull-request verification surface for this repo
#   just dist-host         # build and stage host-platform skill binaries into dist/
#   just hooks-install     # install the local pre-push gate
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

# Run the workspace and repo-level script test suites
test:
  cargo test --workspace --locked
  python3 -m unittest scripts.tests.test_render_table scripts.tests.test_package_skills scripts.tests.test_plugin_port
  python3 -m unittest discover -s skills/excel-foundry/tests -p 'test_*.py'

# Run the plugin portability converter unit tests
test-plugin-port:
  python3 -m unittest scripts.tests.test_plugin_port

# Run opt-in live plugin portability checks against local CLI tools
test-plugin-port-live:
  PLUGIN_PORT_LIVE=1 python3 -m unittest scripts.tests.test_plugin_port_live

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
  python3 scripts/package_skills.py verify-complete

# Smoke-test skill-local launchers against the staged dist payloads
verify-skill-launchers:
  python3 scripts/package_skills.py smoke-launchers

# Run the pull-request verification surface, including packaging checks
ci: bootstrap verify
  @:
  just dist-host
  just verify-packaging
  just verify-skill-launchers

# Install the committed repo-owned pre-push hook for this clone
hooks-install:
  chmod +x githooks/pre-push
  git config --local core.hooksPath githooks
