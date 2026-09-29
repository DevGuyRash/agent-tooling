# Reference solution: every asynchronous child is recorded when it starts and
# waited for by the process that started it. convert settles its own preview
# encode (status included); convert-all records each conversion's PID as it is
# admitted, keeps at most JOBS in flight by reaping the oldest, and reports
# every failure. Both clean up on TERM/INT/HUP once and keep the signal's
# status. Adds tests for early failure, mixed completion order, the slow and
# failing preview, the job limit, and termination.
set -e

cat >bin/convert <<'EOF'
#!/bin/sh
# convert: encode one WAV master as an MP3 plus a 30-second preview clip.
#
# usage: convert SRC OUTDIR
#
# Writes OUTDIR/NAME.mp3 and OUTDIR/NAME.preview.mp3, where NAME is the file
# name of SRC without its .wav extension. Exits 0 only when both were
# written; otherwise it removes both and exits non-zero (128+N when stopped by
# signal N). Either way it returns only after both encodes have finished.
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

main_pid=
preview_pid=

# fail STATUS [MESSAGE]: stop the encodes still running, reap them, remove
# partial output, and exit. Signals are ignored from here on, so a second one
# cannot run the cleanup again or change the status.
fail() {
    trap '' HUP INT TERM
    [ $# -lt 2 ] || echo "convert: $src: $2" >&2
    for pid in $main_pid $preview_pid; do
        kill -TERM "$pid" 2>/dev/null
    done
    for pid in $main_pid $preview_pid; do
        wait "$pid" 2>/dev/null
    done
    rm -f -- "$mp3" "$preview"
    exit "$1"
}
trap 'fail 129' HUP
trap 'fail 130' INT
trap 'fail 143' TERM

# The preview only needs a minute of audio, so it is cut alongside the full
# encode. Both run in the background and are waited for by PID: wait returns
# at once when a signal arrives, and each encode's status counts.
ffmpeg -nostdin -v error -y -ss "$PREVIEW_START" -t 30 -i "$src" \
    -codec:a libmp3lame -b:a 128k "$preview" &
preview_pid=$!
ffmpeg -nostdin -v error -y -i "$src" \
    -codec:a libmp3lame -b:a "$BITRATE" "$mp3" &
main_pid=$!

if wait "$main_pid"; then
    main_pid=
else
    main_pid=
    fail 1 "encoding failed"
fi
if wait "$preview_pid"; then
    preview_pid=
else
    preview_pid=
    fail 1 "preview failed"
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
# Every file is attempted even when others fail, and each failure is reported
# on stderr. Exits 0 when every file converted, 1 when any conversion failed,
# 2 on a usage error, and 128+N when stopped by signal N. In every case it
# returns only after every conversion it started has finished.
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

# Conversions in flight, oldest first: their PIDs, recorded the moment each
# one starts. The file each PID belongs to is kept in file_PID (PIDs are
# digits, so building that name for eval is safe).
running=
nrunning=0
failed=0

# reap_oldest: wait for the oldest conversion in flight and record its result.
# It stays in the list until wait returns, so a signal that interrupts the
# wait still stops it.
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

# stop STATUS: terminate the conversions in flight (each stops its own
# encodes), wait for them, and exit. Signals are ignored from here on, so the
# cleanup runs once and the status stays the first signal's.
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
    # At most $jobs in flight: without wait -n (not in dash or POSIX), the
    # portable bound is to wait for the oldest before starting another.
    [ "$nrunning" -lt "$jobs" ] || reap_oldest
    "$bindir/convert" "$src" "$outdir" &
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

cat >tests/stubs/ffmpeg <<'EOF'
#!/bin/sh
# Stand-in for ffmpeg in the test suite. It accepts the options bin/convert
# uses, rejects input without a RIFF header the way ffmpeg does, and writes a
# small placeholder instead of real audio.
#
# Lines in a fake master steer it: "main_delay=S" or "preview_delay=S" make
# the full encode or the preview (the output given -t) take S seconds, and
# "preview=fail" makes the preview fail after its delay. Until an output is
# finished it holds only a "(partial)" line. With STUB_LOG set, each run
# appends "start PID KIND" and, when it exits, "end PID KIND".
in=
out=
kind=main
while [ $# -gt 0 ]; do
    case $1 in
    -i)
        [ $# -ge 2 ] || break
        in=$2
        shift 2
        ;;
    -t)
        [ $# -ge 2 ] || break
        kind=preview
        shift 2
        ;;
    -ss | -v | -codec:a | -b:a)
        [ $# -ge 2 ] || break
        shift 2
        ;;
    -*) shift ;;
    *)
        out=$1
        shift
        ;;
    esac
done
if [ -z "$in" ] || [ -z "$out" ]; then
    echo "ffmpeg (stub): usage: ffmpeg [options] -i INPUT [options] OUTPUT" >&2
    exit 1
fi

log() {
    [ -z "${STUB_LOG:-}" ] || echo "$1 $$ $kind" >>"$STUB_LOG"
}
log start
trap 'log end' EXIT

header=
IFS= read -r header <"$in" || :
case $header in
RIFF*) ;;
*)
    echo "$in: Invalid data found when processing input" >&2
    exit 1
    ;;
esac

delay=0
outcome=ok
while IFS= read -r line; do
    case $line in
    "${kind}_delay="*) delay=${line#*=} ;;
    "$kind=fail") outcome=fail ;;
    esac
done <"$in"

printf 'ID3 stub (partial)\n' >"$out"
if [ "$delay" != 0 ]; then
    # Sleep in the background so a TERM ends the stub at once.
    sleep "$delay" &
    sleeper=$!
    trap 'kill "$sleeper" 2>/dev/null; exit 143' TERM
    wait "$sleeper"
fi
if [ "$outcome" = fail ]; then
    echo "$out: Conversion failed!" >&2
    exit 1
fi
printf 'ID3 stub mp3 of %s\n' "$in" >"$out"
EOF

cat >>tests/lib.sh <<'EOF'

# slow NAME KEY=VALUE...: create a master whose stub encodes follow the given
# settings (see tests/stubs/ffmpeg), for example main_delay=0.5.
slow() {
    name=$1
    shift
    printf 'RIFF....WAVEfmt \n' >"$name.wav"
    for setting in "$@"; do
        echo "$setting" >>"$name.wav"
    done
}

# complete FILE: FILE is a finished stub encode, not a partial one.
complete() {
    grep -q 'stub mp3 of' "$1" 2>/dev/null
}

# log_encodes: start logging stub encodes to a fresh $STUB_LOG.
log_encodes() {
    STUB_LOG=$WORK/encodes.log
    export STUB_LOG
    : >"$STUB_LOG"
}

# nothing_running: every stub encode that started has also ended.
nothing_running() {
    [ "$(grep -c '^start ' "$STUB_LOG")" -eq "$(grep -c '^end ' "$STUB_LOG")" ]
}

# most_at_once: the most full encodes that were running at the same time.
most_at_once() {
    awk '$3 == "main" && $1 == "start" { n++; if (n > most) most = n }
         $3 == "main" && $1 == "end" { n-- }
         END { print most + 0 }' "$STUB_LOG"
}
EOF

sed '$d' tests/test_convert.sh >tests/test_convert.sh.new
mv tests/test_convert.sh.new tests/test_convert.sh
cat >>tests/test_convert.sh <<'EOF'

# The preview is part of the conversion: convert returns only once it is
# finished, and a failed preview fails the conversion.
log_encodes
slow ep2 main_delay=0.1 preview_delay=1
"$ROOT/bin/convert" ep2.wav out 2>err
check "succeeds when the preview is slower than the MP3" [ $? -eq 0 ]
check "the preview is finished when convert returns" complete out/ep2.preview.mp3
check "no encode is still running when convert returns" nothing_running

slow ep3 preview_delay=0.3 preview=fail
"$ROOT/bin/convert" ep3.wav out 2>err
check "fails when the preview fails" [ $? -ne 0 ]
check "names the master whose preview failed" grep -q 'ep3\.wav' err
check "leaves no MP3 when the preview failed" [ ! -e out/ep3.mp3 ]
check "no encode is still running after a failure" nothing_running

# Terminating convert stops both encodes and removes their partial output.
slow ep4 main_delay=3 preview_delay=3
"$ROOT/bin/convert" ep4.wav out 2>err &
pid=$!
sleep 0.5
kill -TERM "$pid"
wait "$pid"
check "exits 143 when terminated" [ $? -eq 143 ]
check "stops its encodes when terminated" nothing_running
check "removes partial output when terminated" [ ! -e out/ep4.mp3 ]

done_testing
EOF

sed '$d' tests/test_convert_all.sh >tests/test_convert_all.sh.new
mv tests/test_convert_all.sh.new tests/test_convert_all.sh
cat >>tests/test_convert_all.sh <<'EOF'

# A conversion that fails at once, while the ones after it are still running.
log_encodes
corrupt early
for n in late1 late2 late3; do
    slow "$n" main_delay=0.5
done
"$ROOT/bin/convert-all" -o early early.wav late1.wav late2.wav late3.wav >log 2>&1
check "exits 1 when the first conversion fails" [ $? -eq 1 ]
check "names the file that failed" grep -q 'FAILED.*early\.wav' log
for n in late1 late2 late3; do
    check "finishes $n after the early failure" complete "early/$n.mp3"
done
check "nothing is still running after the early failure" nothing_running

# Mixed completion order under a limit: the failure is admitted after a slow
# conversion and finishes long before it.
slow slowest main_delay=0.8
"$ROOT/bin/convert-all" -j 3 -o mixed slowest.wav early.wav ep1.wav ep2.wav >log 2>&1
check "exits 1 when a later, faster conversion fails" [ $? -eq 1 ]
check "names the later failure" grep -q 'FAILED.*early\.wav' log
check "finishes the slow conversion" complete mixed/slowest.mp3

# Previews slower than the MP3s are finished before convert-all returns.
log_encodes
for n in p1 p2 p3; do
    slow "$n" preview_delay=1
done
"$ROOT/bin/convert-all" -o previews p1.wav p2.wav p3.wav >log 2>&1
check "succeeds with slow previews" [ $? -eq 0 ]
for n in p1 p2 p3; do
    check "the $n preview is finished when convert-all returns" complete "previews/$n.preview.mp3"
done
check "nothing is still running when convert-all returns" nothing_running

# A failed preview fails that file and the batch.
slow badpreview preview_delay=0.3 preview=fail
"$ROOT/bin/convert-all" -o badpreview ep1.wav badpreview.wav >log 2>&1
check "exits 1 when a preview fails" [ $? -eq 1 ]
check "names the file whose preview failed" grep -q 'FAILED.*badpreview\.wav' log

# -j bounds the full encodes running at once and still runs that many.
log_encodes
for n in j1 j2 j3 j4 j5; do
    slow "$n" main_delay=0.4
done
"$ROOT/bin/convert-all" -j 2 -o limited j1.wav j2.wav j3.wav j4.wav j5.wav >log 2>&1
check "converts a batch under -j 2" [ $? -eq 0 ]
check "runs exactly two at once under -j 2" [ "$(most_at_once)" -eq 2 ]

# Terminating convert-all stops every conversion before it returns.
log_encodes
for n in t1 t2 t3; do
    slow "$n" main_delay=3 preview_delay=3
done
"$ROOT/bin/convert-all" -o stopped t1.wav t2.wav t3.wav >log 2>&1 &
pid=$!
sleep 0.5
kill -TERM "$pid"
wait "$pid"
check "exits 143 when terminated" [ $? -eq 143 ]
check "stops every conversion when terminated" nothing_running

done_testing
EOF

cat >"$TRIAL_JOB_DIR/final-0.md" <<'EOF'
Fixed. convert-all kept only the last conversion's PID and reaped the rest with a bare `wait`, which always succeeds, so an early failure was lost. It now records each conversion's PID when it starts, waits for every one by PID (at most -j in flight, reaping the oldest, since `wait -n` is not available in dash), reports each failed file, and exits 1. convert also started its preview encode in the background and never waited for it, so convert (and the batch) could return while previews were still being written, and a failed preview was ignored; it now waits for both encodes and fails if either does. Both scripts stop their children on TERM/INT/HUP and exit with the signal's status. Tests cover early and out-of-order failures, slow and failing previews, the job limit, and termination; `sh tests/run.sh` passes.
EOF
