# Reference behavior (alternative correct): the same correct behavior as good.sh, but the
# agent also commits its work. Regression arm: committing must not hide the change from the
# checks (which read git diff/status against the initial commit, not just the working tree).
set -e
. "$(dirname "$0")/lib/tl-rows.sh"

{ echo "Month,Milestone"; echo "$TL_ROWS"; } > timeline.csv
sed -i 's/- Timeline: not started\./- Timeline: done (`timeline.csv`)./' STATUS.md
git add -A && git commit -q -m "Add grant timeline"

cat > "$TRIAL_JOB_DIR/final-0.md" <<'MSG'
Added and committed timeline.csv. All three deliverables done; left the Next suggestions alone.
MSG
