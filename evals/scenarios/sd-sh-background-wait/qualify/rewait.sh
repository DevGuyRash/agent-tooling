# Partial: the reference convert (and the original tests), with a convert-all
# that keeps the bare `wait` and afterwards asks for each recorded PID's
# status. BusyBox ash remembers the status of children a bare wait already
# reaped, so this looks right there; bash running as sh forgets all but $!,
# so every round reports false failures. (dash is not available to test.)
set -e
sh "$TRIAL_SCENARIO_DIR/qualify/good.sh"
rm -rf tests
cp -Rp "$TRIAL_SCENARIO_DIR/fixture/tests" tests

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

# collect: let the round finish, then look up how each conversion ended.
collect() {
    wait
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

cat >"$TRIAL_JOB_DIR/final-0.md" <<'EOF'
Fixed. After each round convert-all still waits for everything, then checks how each recorded conversion ended, reports every failed file, and exits 1. convert waits for its preview encode and fails if it fails.
EOF
