# project-harness: managed-file
# Example only: minimal harness for a repo with no clear build surface yet.
# Replace every placeholder before treating this as authoritative.
# Usage examples:
#   just bootstrap         # replace with your real setup command
#   just test              # replace with your real test runner
#   just build             # replace with your real build command

set shell := ["bash", "-euo", "pipefail", "-c"]

# Show the recipe catalog and short descriptions
default:
    @just --list

# Install dependencies, tooling, and local prerequisites for normal development
bootstrap:
    @echo "Replace with dependency installation"

# Rewrite source files into the canonical project style
fmt:
    @echo "Replace with formatter command"

# Verify formatting without rewriting source files
fmt-check:
    @echo "Replace with formatting check command"

# Run static analysis and policy checks
lint:
    @echo "Replace with linter command"

# Run the repo's automated test surface
test:
    @echo "Replace with test command"

# Compile the detected project surfaces in the default build profile
build:
    @echo "Replace with build command"

# Run the pull-request verification surface in local sequence
ci:
    just fmt-check
    just lint
    just test
