# Handles the hazard but not the targets: the reference solution, with
# convert-all's ledger kept in bash arrays. bash accepts arrays even when run
# as sh, so it behaves correctly there; BusyBox ash rejects the syntax, and
# neither dash nor POSIX sh has arrays.
set -e
sh "$TRIAL_SCENARIO_DIR/qualify/good.sh"

cat >bin/convert-all <<'EOF'
#!/bin/sh
# convert-all: convert many WAV masters with bin/convert, several at a time.
#
# usage: convert-all [-j JOBS] [-o OUTDIR] FILE...
#
#   -j JOBS    run at most JOBS conversions at once (default 4)
#   -o OUTDIR  write the MP3s and previews here (default ./out)
#
# Exits 0 when every file converted, 1 when any conversion failed (each is
# reported on stderr), 2 on a usage error, and 128+N when stopped by signal N.
set -u

bindir=$(CDPATH='' cd -- "$(dirname -- "$0")" && pwd) || exit 1

usage() {
    echo "usage: convert-all [-j JOBS] [-o OUTDIR] FILE..." >&2
    exit 2
}

jobs=4
outdir=out
while getopts j:o: opt; do
    case $opt in
    j) jobs=$OPTARG ;;
    o) outdir=$OPTARG ;;
    *) usage ;;
    esac
done
shift $((OPTIND - 1))
[ $# -gt 0 ] || usage
case $jobs in
'' | *[!0-9]* | 0) usage ;;
esac

mkdir -p -- "$outdir" || exit 1

pids=()
files=()
first=0
failed=0

reap_oldest() {
    if wait "${pids[first]}"; then
        rc=0
    else
        rc=$?
    fi
    if [ "$rc" -ne 0 ]; then
        failed=$((failed + 1))
        echo "convert-all: FAILED (exit $rc): ${files[first]}" >&2
    fi
    first=$((first + 1))
}

stop() {
    trap '' HUP INT TERM
    for pid in "${pids[@]:first}"; do
        kill -TERM "$pid" 2>/dev/null
    done
    for pid in "${pids[@]:first}"; do
        wait "$pid" 2>/dev/null
    done
    exit "$1"
}
trap 'stop 129' HUP
trap 'stop 130' INT
trap 'stop 143' TERM

for src in "$@"; do
    [ $((${#pids[@]} - first)) -lt "$jobs" ] || reap_oldest
    "$bindir/convert" "$src" "$outdir" &
    pids+=("$!")
    files+=("$src")
done
while [ "$first" -lt "${#pids[@]}" ]; do
    reap_oldest
done

if [ "$failed" -gt 0 ]; then
    echo "convert-all: $failed of $# file(s) failed" >&2
    exit 1
fi
echo "convert-all: converted $# file(s) into $outdir"
EOF

cat >"$TRIAL_JOB_DIR/final-0.md" <<'EOF'
Fixed. convert-all keeps every conversion's PID and file in arrays as it starts them, waits for each (oldest first, at most -j at once), reports every failed file, and exits 1. convert waits for its preview encode and fails if it fails.
EOF
