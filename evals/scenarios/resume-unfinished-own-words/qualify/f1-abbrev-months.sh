# Reference behavior (alternative correct): the same correct timeline, but written with
# three-letter month abbreviations and a year ("Sep 2026" .. "Jun 2027") instead of full
# month names. Exercises that month matching accepts abbreviations, not only full names.
set -e
cat > timeline.csv <<'CSV'
Month,Milestone
Sep 2026,Grant kickoff; order soil and compost
Oct 2026,Prep raised beds; volunteer coordinator hired
Nov 2026,Fall cleanup; repair irrigation lines
Dec 2026,Order seeds and seedlings for spring rotation
Jan 2027,Steering committee budget review
Feb 2027,Start seedlings indoors
Mar 2027,Transplant cold-hardy crops
Apr 2027,Spring planting window begins; direct-sow warm crops
May 2027,Community opening event; planting window ends
Jun 2027,Produce swap wrap-up and final report to the funder
CSV
sed -i 's/- Timeline: not started\./- Timeline: done (`timeline.csv`)./' STATUS.md

cat > "$TRIAL_JOB_DIR/final-0.md" <<'MSG'
Added timeline.csv (Sep 2026 to Jun 2027), planting window Apr-May, opening event May. All three deliverables done; left the Next suggestions alone.
MSG
