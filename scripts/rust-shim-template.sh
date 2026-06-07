#!/usr/bin/env sh
set -eu

# Template for plugin-local skill packaged-binary launchers.
# Copy this file into a plugin-local skill's scripts/ directory and replace:
#   __BIN_NAME__    binary name (example: docker-architect-compose)

script_path="$0"

case "$script_path" in
  */*) : ;;
  *)
    resolved="$(command -v -- "$script_path" 2>/dev/null || true)"
    case "$resolved" in
      */*) script_path="$resolved" ;;
    esac
    ;;
esac

if command -v readlink >/dev/null 2>&1; then
  while [ -L "$script_path" ]; do
    link="$(readlink "$script_path" 2>/dev/null || true)"
    [ -n "$link" ] || break
    case "$link" in
      /*) script_path="$link" ;;
      *) script_path="$(dirname -- "$script_path")/$link" ;;
    esac
  done
fi

script_dir="$(CDPATH= cd -- "$(dirname -- "$script_path")" && pwd)"
skill_root="$(CDPATH= cd -- "${script_dir}/.." && pwd)"
os_name="$(uname -s 2>/dev/null || echo unknown)"
arch_name="$(uname -m 2>/dev/null || echo unknown)"

if [ "$os_name" != "Linux" ]; then
  echo "error: this launcher only supports Linux hosts (got ${os_name})" >&2
  exit 2
fi
case "$arch_name" in
  x86_64|amd64) platform_arch="x86_64" ;;
  arm64|aarch64) platform_arch="aarch64" ;;
  *)
    echo "error: unsupported host architecture: ${arch_name}" >&2
    exit 2
    ;;
esac

platform_id="linux-${platform_arch}"
bin_name="__BIN_NAME__"
bin="${skill_root}/dist/${platform_id}/${bin_name}"

if [ ! -x "${bin}" ] || [ ! -f "${bin}" ] || [ -L "${bin}" ]; then
  echo "error: missing packaged binary at ${bin}" >&2
  echo "hint: run 'just dist-host' from the repo root or fetch refreshed dist outputs from CI" >&2
  exit 127
fi

if find "${bin}" -prune -perm -002 -print -quit | grep -q .; then
  echo "error: refusing to execute world-writable binary: ${bin}" >&2
  exit 2
fi

exec "${bin}" "$@"
