# Reference behavior (alternative correct): the same correct timeline, but under a
# differently-cased filename (Timeline.md) than the fixed list's exact-case entries.
# Exercises that filename case doesn't gate recognition.
set -e
. "$(dirname "$0")/lib/tl-rows.sh"

{ echo "# Timeline"; echo; echo "$TL_ROWS" | sed 's/^/- /'; } > Timeline.md
sed -i 's/- Timeline: not started\./- Timeline: done (`Timeline.md`)./' STATUS.md

cat > "$TRIAL_JOB_DIR/final-0.md" <<'MSG'
Added Timeline.md. All three deliverables done; left the Next suggestions alone.
MSG
