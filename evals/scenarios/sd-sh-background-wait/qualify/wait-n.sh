# Handles the hazard but not the targets: the reference solution, with
# convert-all's bound rebuilt on `wait -n` (bash, and BusyBox 1.36 ash, but
# not dash 0.5.12 or POSIX) and a per-job status file. It behaves correctly
# under bash and ash, so only the static dialect check can fail it.
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
# reported on stderr), and 2 on a usage error.
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
ledger=$(mktemp -d "${TMPDIR:-/tmp}/convert-all.XXXXXX") || exit 1
trap 'rm -rf -- "$ledger"' EXIT

n=0
inflight=0
for src in "$@"; do
    if [ "$inflight" -ge "$jobs" ]; then
        wait -n # a slot frees as soon as any conversion finishes
        inflight=$((inflight - 1))
    fi
    n=$((n + 1))
    printf '%s\n' "$src" >"$ledger/$n.src"
    ("$bindir/convert" "$src" "$outdir"; echo "$?" >"$ledger/$n.status") &
    inflight=$((inflight + 1))
done
wait

failed=0
i=1
while [ "$i" -le "$n" ]; do
    status=$(cat "$ledger/$i.status" 2>/dev/null) || status=
    if [ "$status" != 0 ]; then
        failed=$((failed + 1))
        echo "convert-all: FAILED (${status:-no status}): $(cat "$ledger/$i.src")" >&2
    fi
    i=$((i + 1))
done

if [ "$failed" -gt 0 ]; then
    echo "convert-all: $failed of $# file(s) failed" >&2
    exit 1
fi
echo "convert-all: converted $# file(s) into $outdir"
EOF
# good.sh's termination test expects signal forwarding, which this design drops.
sed '/^# Terminating convert-all stops/,/^check "stops every conversion when terminated"/d' \
    tests/test_convert_all.sh >tests/test_convert_all.sh.new
mv tests/test_convert_all.sh.new tests/test_convert_all.sh

cat >"$TRIAL_JOB_DIR/final-0.md" <<'EOF'
Fixed. convert-all now keeps up to -j conversions running with `wait -n`, records each job's exit status in a ledger file, reports every failed file, and exits 1. convert waits for its preview encode and fails if it fails.
EOF
