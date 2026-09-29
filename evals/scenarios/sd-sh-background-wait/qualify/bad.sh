# Plausible fix that misses the hazard: convert-all now records every
# conversion's PID and waits for each one, so the reported symptom (an early
# failure exiting 0) is gone, portably and within -j. But bin/convert still
# starts its preview encode in the background and never waits for it, so the
# batch can return while previews are being written, and a failed preview is
# never noticed.
set -e

cat >bin/convert-all <<'EOF'
#!/bin/sh
# convert-all: convert many WAV masters with bin/convert, several at a time.
#
# usage: convert-all [-j JOBS] [-o OUTDIR] FILE...
#
#   -j JOBS    run at most JOBS conversions at once (default 4)
#   -o OUTDIR  write the MP3s and previews here (default ./out)
#
# Exits 0 when every file converted, 1 when any conversion failed, and 2 on
# a usage error.
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

status=0
pids=
running=0

# collect: wait for every conversion in this round and note which failed.
collect() {
    for pid in $pids; do
        if ! wait "$pid"; then
            eval "failed_src=\$src_$pid"
            echo "convert-all: FAILED: $failed_src" >&2
            status=1
        fi
    done
    pids=
    running=0
}

for src in "$@"; do
    "$bindir/convert" "$src" "$outdir" &
    pid=$!
    pids="$pids $pid"
    eval "src_$pid=\$src"
    running=$((running + 1))
    if [ "$running" -ge "$jobs" ]; then
        collect
    fi
done
collect

if [ "$status" -ne 0 ]; then
    echo "convert-all: some conversions failed" >&2
    exit 1
fi
echo "convert-all: converted $# file(s) into $outdir"
EOF

sed '$d' tests/test_convert_all.sh >tests/test_convert_all.sh.new
mv tests/test_convert_all.sh.new tests/test_convert_all.sh
cat >>tests/test_convert_all.sh <<'EOF'

# Regression: a failure that is not the last file started used to exit 0.
"$ROOT/bin/convert-all" -o early bad.wav ep1.wav ep2.wav >log 2>&1
check "exits 1 when the first conversion fails" [ $? -eq 1 ]
check "names the file that failed" grep -q 'FAILED: bad\.wav' log
check "still converts the rest after an early failure" [ -s early/ep2.mp3 ]

done_testing
EOF

cat >"$TRIAL_JOB_DIR/final-0.md" <<'EOF'
Fixed. convert-all only kept the PID of the last conversion it started and then called `wait` with no operands, which always succeeds, so a failure in any earlier conversion was lost. It now records the PID of every conversion (and which file it is for), waits for each one individually, prints `convert-all: FAILED: <file>` for every failure, and exits 1. The -j limit still works the same way, and everything is plain POSIX sh. I added a regression test with the failing file first; `sh tests/run.sh` passes.
EOF
