#!/bin/sh
set -eu

SCRIPT_DIR=$(CDPATH='' cd -- "$(dirname "$0")" && pwd)
REPO_ROOT=$(CDPATH='' cd -- "${SCRIPT_DIR}/.." && pwd)
BIN="${REPO_ROOT}/target/release/render-table"

if [ ! -x "$BIN" ]; then
  if ! command -v cargo >/dev/null 2>&1; then
    printf 'render-table.sh: missing %s and cargo is unavailable\n' "$BIN" >&2
    exit 127
  fi
  cargo build --manifest-path "${REPO_ROOT}/Cargo.toml" --locked --release -p render-table >/dev/null
fi

exec "$BIN" "$@"
