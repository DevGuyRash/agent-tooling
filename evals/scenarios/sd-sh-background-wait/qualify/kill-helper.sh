# Partial: the reference convert-all (and the original tests), with a convert
# that "cleans up" its background preview encode by killing it once the MP3
# is done instead of waiting for it. Nothing is left running, but a preview
# slower than the MP3 is cut short, and a preview that fails late is never
# noticed.
set -e
sh "$TRIAL_SCENARIO_DIR/qualify/good.sh"
rm -rf tests
cp -Rp "$TRIAL_SCENARIO_DIR/fixture/tests" tests

cat >bin/convert <<'EOF'
#!/bin/sh
# convert: encode one WAV master as an MP3 plus a 30-second preview clip.
#
# usage: convert SRC OUTDIR
#
# Writes OUTDIR/NAME.mp3 and OUTDIR/NAME.preview.mp3, where NAME is the file
# name of SRC without its .wav extension. Exits non-zero if encoding fails.
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

# The preview only needs a minute of audio, so cut it alongside the full
# encode; it must not outlive this script.
ffmpeg -nostdin -v error -y -ss "$PREVIEW_START" -t 30 -i "$src" \
    -codec:a libmp3lame -b:a 128k "$preview" &
preview_pid=$!
trap 'kill "$preview_pid" 2>/dev/null; wait "$preview_pid" 2>/dev/null' EXIT

if ! ffmpeg -nostdin -v error -y -i "$src" \
    -codec:a libmp3lame -b:a "$BITRATE" "$mp3"; then
    echo "convert: $src: encoding failed" >&2
    rm -f -- "$mp3"
    exit 1
fi
EOF

cat >"$TRIAL_JOB_DIR/final-0.md" <<'EOF'
Fixed. convert-all now records every conversion's PID, waits for each one, reports every failed file, and exits 1. convert no longer leaves its background preview encode running: an EXIT trap stops and reaps it, so nothing outlives the batch.
EOF
