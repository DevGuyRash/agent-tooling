#!/usr/bin/env sh
set -eu
if ! command -v python3 >/dev/null 2>&1; then
    echo 'error: script_sanity requires Python 3' >&2
    echo 'hint: use a host with Python 3, or inspect the scripts directly' >&2
    exit 2
fi
exec python3 -B "$(dirname "$0")/script_sanity.py" "$@"
