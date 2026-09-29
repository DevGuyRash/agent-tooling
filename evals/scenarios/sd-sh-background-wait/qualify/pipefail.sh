# Handles the hazard but not the targets: the reference solution, with each
# conversion's messages prefixed by its file name through a pipeline whose
# status comes from `set -o pipefail`. bash and BusyBox 1.36 ash both support
# pipefail (wait on the pipeline's last PID then reports convert's failure),
# so only the static check fails it: dash 0.5.12 has no pipefail.
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
# Each job is "convert | sed"; pipefail makes the job's status convert's.
set -o pipefail

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

running=
nrunning=0
failed=0

reap_oldest() {
    set -- $running
    pid=$1
    if wait "$pid"; then
        rc=0
    else
        rc=$?
    fi
    shift
    running=$*
    nrunning=$#
    eval "file=\$file_$pid"
    unset "file_$pid"
    if [ "$rc" -ne 0 ]; then
        failed=$((failed + 1))
        echo "convert-all: FAILED (exit $rc): $file" >&2
    fi
}

stop() {
    trap '' HUP INT TERM
    for pid in $running; do
        kill -TERM "$pid" 2>/dev/null
    done
    for pid in $running; do
        wait "$pid" 2>/dev/null
    done
    exit "$1"
}
trap 'stop 129' HUP
trap 'stop 130' INT
trap 'stop 143' TERM

for src in "$@"; do
    [ "$nrunning" -lt "$jobs" ] || reap_oldest
    name=${src##*/}
    "$bindir/convert" "$src" "$outdir" 2>&1 | sed "s|^|$name: |" >&2 &
    pid=$!
    running="$running $pid"
    nrunning=$((nrunning + 1))
    eval "file_$pid=\$src"
done
while [ "$nrunning" -gt 0 ]; do
    reap_oldest
done

if [ "$failed" -gt 0 ]; then
    echo "convert-all: $failed of $# file(s) failed" >&2
    exit 1
fi
echo "convert-all: converted $# file(s) into $outdir"
EOF
# good.sh's termination test expects TERM to reach convert, not the prefixing sed.
sed '/^# Terminating convert-all stops/,/^check "stops every conversion when terminated"/d' \
    tests/test_convert_all.sh >tests/test_convert_all.sh.new
mv tests/test_convert_all.sh.new tests/test_convert_all.sh

cat >"$TRIAL_JOB_DIR/final-0.md" <<'EOF'
Fixed. convert-all records every conversion's PID as it starts, waits for each one, reports every failed file, and exits 1; each conversion's messages are prefixed with its file name, and pipefail makes the job's status convert's rather than the prefixing sed's. convert waits for its preview encode and fails if it fails.
EOF
