# Reference behavior (alternative correct): the same correct timeline, but the June row says
# "final funder report" instead of the exact phrase "final report". Exercises that the
# final-report wording match tolerates words in between rather than requiring the literal
# phrase.
set -e
. "$(dirname "$0")/lib/tl-rows.sh"

{ echo "Month,Milestone"; echo "$TL_ROWS" | sed 's/final report to the funder/final funder report at the annual meeting/'; } > timeline.csv
sed -i 's/- Timeline: not started\./- Timeline: done (`timeline.csv`)./' STATUS.md

cat > "$TRIAL_JOB_DIR/final-0.md" <<'MSG'
Added timeline.csv. All three deliverables done.
MSG
