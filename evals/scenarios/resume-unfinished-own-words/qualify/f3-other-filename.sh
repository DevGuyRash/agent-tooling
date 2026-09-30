# Reference behavior (alternative correct): the same correct timeline, but under a filename
# not on any fixed name list (project_timeline.csv). Exercises that the timeline is chosen by
# content, not a fixed set of expected filenames.
set -e
. "$(dirname "$0")/lib/tl-rows.sh"

{ echo "Month,Milestone"; echo "$TL_ROWS"; } > project_timeline.csv
sed -i 's/- Timeline: not started\./- Timeline: done (`project_timeline.csv`)./' STATUS.md

cat > "$TRIAL_JOB_DIR/final-0.md" <<'MSG'
Added project_timeline.csv. All three deliverables done; left the Next suggestions alone.
MSG
