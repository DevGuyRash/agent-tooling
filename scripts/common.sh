#!/usr/bin/env sh

log() {
  prefix="$1"
  shift
  printf '%s\n' "${prefix}: $*" >&2
}

build_rust_skill() {
  prefix="$1"
  name="$2"
  skip_flag_value="$3"
  skip_flag_name="$4"
  manifest_path="$5"
  action_prefix="$6"

  if [ "${skip_flag_value}" = "1" ]; then
    log "$prefix" "skipping ${name} prebuild (${skip_flag_name}=1)"
  else
    log "$prefix" "${action_prefix} ${name} binaries (locked, release)"
    cargo build --manifest-path "${manifest_path}" --locked --release
  fi
}

resolve_deprecated_flag() {
  prefix="$1"
  preferred_flag_name="$2"
  preferred_value="$3"
  deprecated_flag_name="$4"
  deprecated_value="$5"

  if [ -z "${preferred_value}" ] && [ -n "${deprecated_value}" ]; then
    log "$prefix" "warning: ${deprecated_flag_name} is deprecated; use ${preferred_flag_name}"
    printf '%s' "${deprecated_value}"
    return 0
  fi

  printf '%s' "${preferred_value}"
}
