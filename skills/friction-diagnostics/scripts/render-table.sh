#!/bin/sh
set -eu

SCRIPT_DIR=$(CDPATH='' cd -- "$(dirname "$0")" && pwd)
SKILL_ROOT=$(CDPATH='' cd -- "${SCRIPT_DIR}/.." && pwd)
OS_NAME=$(uname -s 2>/dev/null || echo unknown)
ARCH_NAME=$(uname -m 2>/dev/null || echo unknown)

case "$OS_NAME" in
  Linux) PLATFORM_OS="linux" ;;
  Darwin) PLATFORM_OS="macos" ;;
  MINGW*|MSYS*|CYGWIN*|Windows_NT) PLATFORM_OS="windows" ;;
  *)
    printf 'render-table.sh: unsupported host OS: %s\n' "$OS_NAME" >&2
    exit 2
    ;;
esac
case "$ARCH_NAME" in
  x86_64|amd64) PLATFORM_ARCH="x86_64" ;;
  arm64|aarch64) PLATFORM_ARCH="aarch64" ;;
  *)
    printf 'render-table.sh: unsupported host architecture: %s\n' "$ARCH_NAME" >&2
    exit 2
    ;;
esac

PLATFORM_ID="${PLATFORM_OS}-${PLATFORM_ARCH}"
BIN_NAME="render-table"
[ "$PLATFORM_OS" = "windows" ] && BIN_NAME="${BIN_NAME}.exe"
BIN="${SKILL_ROOT}/dist/${PLATFORM_ID}/${BIN_NAME}"

if [ ! -x "$BIN" ] || [ ! -f "$BIN" ] || [ -L "$BIN" ]; then
  printf 'render-table.sh: missing packaged renderer at %s\n' "$BIN" >&2
  printf "hint: run 'just dist-host' from the repo root or fetch refreshed dist outputs from CI\n" >&2
  exit 127
fi

exec "$BIN" "$@"
