# Repo command surface for plugin-local skill packaging, launcher validation, and local verification.
# Usage examples:
#   just bootstrap         # install packaging prerequisites used by repo scripts
#   just verify            # run the fast local verification surface
#   just ci                # run the pull-request verification surface for this repo
#   just dist-host         # build and stage host-platform plugin-local skill binaries into dist/
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
  python3 -m unittest scripts.tests.test_render_table scripts.tests.test_package_skills scripts.tests.test_plugin_port scripts.tests.test_install_all scripts.tests.test_install_all_scope scripts.tests.test_agentic_plugin scripts.tests.test_audit_plugins scripts.tests.test_plugin_port_live.ProfileSelectionTests
  python3 -m unittest discover -s plugins/excel-foundry/skills/excel-foundry/tests -p 'test_*.py'
  PYTHONDONTWRITEBYTECODE=1 python3 -m unittest discover -s plugins/software-development/tests -p 'test_*.py'
  PYTHONDONTWRITEBYTECODE=1 python3 -m unittest discover -s plugins/agentic-design-and-evaluation/skills/skill-auditor/tests -p 'test_*.py'
  bash plugins/friction-diagnostics/skills/friction-diagnostics/tests/smoke-posix.sh

# Run the friction-diagnostics plugin smoke suite (POSIX)
test-friction-diagnostics:
  bash plugins/friction-diagnostics/skills/friction-diagnostics/tests/smoke-posix.sh

# Run the optional structural reporters over every plugin, or the named ones
audit-plugins *args:
  scripts/audit-plugins.sh {{args}}

# Run the plugin portability converter unit tests
test-plugin-port:
  python3 -m unittest scripts.tests.test_plugin_port

# Run live checks; opt into each host with PLUGIN_PORT_CODEX=1 / PLUGIN_PORT_CLAUDE=1
test-plugin-port-live:
  PLUGIN_PORT_LIVE=1 python3 -m unittest scripts.tests.test_plugin_port_live

# Reconcile selected agent-tooling plugins in Codex and Claude Code by artifact identity
install-all *args:
  scripts/install-all {{args}}

# Compile the Rust workspace in the default build profile
build:
  cargo build --workspace --locked

# Build and stage host-platform packaged binaries into plugin-local skill dist/ directories
dist-host:
  python3 scripts/package_skills.py stage-host

# Run the fast local verification surface without packaging steps
verify: fmt-check lint test

# Render the Project Harness candidate files under .local/harness/render
harness-render:
  python3 plugins/project-harness/skills/project-harness/scripts/project_harness.py render . --pretty

# Inspect the Project Harness view of this repo and local tool availability
harness-doctor:
  python3 plugins/project-harness/skills/project-harness/scripts/project_harness.py doctor . --pretty

# Verify committed packaging policy and staged deliverables for the current host
verify-packaging:
  python3 scripts/package_skills.py verify-host
  python3 scripts/package_skills.py verify-complete

# Smoke-test plugin-local skill launchers against the staged dist payloads
verify-skill-launchers:
  python3 scripts/package_skills.py smoke-launchers

# Run the pull-request verification surface without rewriting tracked dist payloads
ci: bootstrap verify verify-skill-launchers
  @:

# Install the committed repo-owned pre-push gate for this clone
hooks-install:
  chmod +x githooks/pre-push
  git config --local core.hooksPath githooks
