# project-harness: managed-file
# Example only: minimal harness for a repo with no clear build surface yet.
# Replace every placeholder before treating this as authoritative.

set shell := ["bash", "-euo", "pipefail", "-c"]

default:
    @just --list

# Install dependencies and prepare the repo
bootstrap:
    @echo "Replace with dependency installation"

# Format code
fmt:
    @echo "Replace with formatter command"

# Check formatting without changing files
fmt-check:
    @echo "Replace with formatting check command"

# Run linters
lint:
    @echo "Replace with linter command"

# Run tests
test:
    @echo "Replace with test command"

# Build the project
build:
    @echo "Replace with build command"

# Run the normal CI surface
ci:
    just fmt-check
    just lint
    just test
