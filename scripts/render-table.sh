#!/bin/sh
set -eu

SCRIPT_DIR=$(CDPATH='' cd -- "$(dirname "$0")" && pwd)
REPO_ROOT=$(CDPATH='' cd -- "${SCRIPT_DIR}/.." && pwd)
BIN="${REPO_ROOT}/target/release/render-table"

if command -v cargo >/dev/null 2>&1; then
  exec cargo run --manifest-path "${REPO_ROOT}/Cargo.toml" --locked --release --quiet -p render-table -- "$@"
fi

# Without Cargo, only the existing default-location standalone binary is known.
if [ -n "${CARGO_TARGET_DIR:-}" ] || [ -n "${CARGO_BUILD_TARGET:-}" ]; then
  printf 'render-table.sh: cargo is required to resolve the selected target\n' >&2
  exit 127
fi
if [ ! -x "$BIN" ]; then
  printf 'render-table.sh: missing %s and cargo is unavailable\n' "$BIN" >&2
  exit 127
fi

exec "$BIN" "$@"
