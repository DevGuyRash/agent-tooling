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
