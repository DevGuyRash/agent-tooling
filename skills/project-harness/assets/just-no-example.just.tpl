# project-harness: managed-file
# Example only: minimal harness for a repo with no clear build surface yet.
# Replace every placeholder before treating this as authoritative.

set shell := ["bash", "-euo", "pipefail", "-c"]

default:
    @just --list

bootstrap:
    @echo "Replace with dependency installation"

fmt:
    @echo "Replace with formatter command"

fmt-check:
    @echo "Replace with formatting check command"

lint:
    @echo "Replace with linter command"

test:
    @echo "Replace with test command"

build:
    @echo "Replace with build command"

ci:
    just fmt-check
    just lint
    just test
