# Another correct design, written independently of good.sh: convert runs the
# preview after the full encode (no background helper at all), and convert-all
# runs rounds of JOBS, each job a subshell that writes its exit status to a
# file. The bare `wait` is only synchronization; the status ledger is the
# files, and a missing status counts as a failure. Must pass every required
# check. (It does not forward signals, so the interrupt measures may fail.)
set -e

cat >bin/convert <<'EOF'
#!/bin/sh
# convert: encode one WAV master as an MP3 plus a 30-second preview clip.
#
# usage: convert SRC OUTDIR
#
# Writes OUTDIR/NAME.mp3 and OUTDIR/NAME.preview.mp3, where NAME is the file
# name of SRC without its .wav extension. Exits 0 only when both were
# written; on failure it removes both and exits 1.
set -u

usage() {
    echo "usage: convert SRC OUTDIR" >&2
    exit 2
}

[ $# -eq 2 ] || usage
src=$1
outdir=$2
if [ ! -f "$src" ]; then
    echo "convert: $src: no such file" >&2
    exit 1
fi

name=${src##*/}
name=${name%.wav}
mp3=$outdir/$name.mp3
preview=$outdir/$name.preview.mp3

: "${BITRATE:=192k}"
: "${PREVIEW_START:=30}"

if ! ffmpeg -nostdin -v error -y -i "$src" \
    -codec:a libmp3lame -b:a "$BITRATE" "$mp3"; then
    echo "convert: $src: encoding failed" >&2
    rm -f -- "$mp3"
    exit 1
fi
if ! ffmpeg -nostdin -v error -y -ss "$PREVIEW_START" -t 30 -i "$src" \
    -codec:a libmp3lame -b:a 128k "$preview"; then
    echo "convert: $src: preview failed" >&2
    rm -f -- "$mp3" "$preview"
    exit 1
fi
EOF

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
trap 'exit 129' HUP
trap 'exit 130' INT
trap 'exit 143' TERM

n=0
inround=0
for src in "$@"; do
    n=$((n + 1))
    printf '%s\n' "$src" >"$ledger/$n.src"
    ("$bindir/convert" "$src" "$outdir"; echo "$?" >"$ledger/$n.status") &
    inround=$((inround + 1))
    if [ "$inround" -ge "$jobs" ]; then
        wait # every job in the round records its own status
        inround=0
    fi
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

cat >"$TRIAL_JOB_DIR/final-0.md" <<'EOF'
Fixed. Each conversion now records its exit status in a ledger file, and convert-all reports every failed file and exits 1; a bare `wait` alone always returns 0, which is why the early failure was lost. convert used to start the preview encode in the background without waiting for it; it now encodes the preview after the MP3 and fails if either fails, so nothing is still running when it returns.
EOF
