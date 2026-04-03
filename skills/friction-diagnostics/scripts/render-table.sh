#!/bin/sh
set -eu

SCRIPT_DIR=$(CDPATH='' cd -- "$(dirname "$0")" && pwd)
ROOT_RENDER="$SCRIPT_DIR/../../../scripts/render-table.sh"

if [ ! -f "$ROOT_RENDER" ]; then
  printf 'render-table.sh: missing shared renderer at %s\n' "$ROOT_RENDER" >&2
  exit 1
fi

exec sh "$ROOT_RENDER" "$@"
