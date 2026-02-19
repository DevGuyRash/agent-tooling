#!/usr/bin/env sh
set -eu

# Template for skill-local Rust binary shims.
# Copy this file into a skill's scripts/ directory and replace:
#   __BIN_NAME__    binary name (example: docker-architect-compose)
#   __TOOLING_DIR__ path from script_dir to crate workspace root
#   __MANIFEST__    manifest path relative to tooling dir (example: docker-architect-compose/Cargo.toml)
#   __SRC_DIRS__    one or more source directories under tooling dir

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
tooling_dir="${script_dir}/__TOOLING_DIR__"
manifest_path="${tooling_dir}/__MANIFEST__"
lock_path="${tooling_dir}/Cargo.lock"
bin="${tooling_dir}/target/release/__BIN_NAME__"

if [ ! -f "${manifest_path}" ]; then
  echo "error: missing ${manifest_path}" >&2
  exit 2
fi

if [ ! -f "${lock_path}" ]; then
  echo "error: missing ${lock_path} (workspace is expected to be shipped with a lockfile)" >&2
  exit 2
fi

needs_build=0
if [ ! -x "${bin}" ] || [ ! -f "${bin}" ] || [ -L "${bin}" ]; then
  needs_build=1
elif [ "${manifest_path}" -nt "${bin}" ] || [ "${lock_path}" -nt "${bin}" ]; then
  needs_build=1
else
  src_check_failed=0
  for src_dir in __SRC_DIRS__; do
    if [ ! -d "${src_dir}" ] || [ ! -r "${src_dir}" ]; then
      src_check_failed=1
      break
    fi
  done

  if [ "${src_check_failed}" -eq 1 ]; then
    needs_build=1
  elif find __SRC_DIRS__ -type f -newer "${bin}" -print -quit | grep -q .; then
    needs_build=1
  fi
fi

if [ "${needs_build}" -eq 1 ]; then
  if ! command -v cargo >/dev/null 2>&1; then
    echo "error: __BIN_NAME__ is not built and 'cargo' was not found in PATH" >&2
    exit 127
  fi
  cargo build --manifest-path "${manifest_path}" --locked --release
fi

if [ ! -x "${bin}" ] || [ ! -f "${bin}" ] || [ -L "${bin}" ]; then
  echo "error: refusing to execute an invalid binary path: ${bin}" >&2
  exit 2
fi

if find "${bin}" -prune -perm -002 -print -quit | grep -q .; then
  echo "error: refusing to execute world-writable binary: ${bin}" >&2
  exit 2
fi

exec "${bin}" "$@"
