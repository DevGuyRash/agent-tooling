# Reference behavior (alternative correct): the same correct timeline, but written with ISO
# "YYYY-MM" dates ("2026-09" .. "2027-06") instead of month names. Exercises that month
# matching accepts numeric dates, not only names.
set -e
cat > timeline.csv <<'CSV'
Month,Milestone
2026-09,Grant kickoff; order soil and compost
2026-10,Prep raised beds; volunteer coordinator hired
2026-11,Fall cleanup; repair irrigation lines
2026-12,Order seeds and seedlings for spring rotation
2027-01,Steering committee budget review
2027-02,Start seedlings indoors
2027-03,Transplant cold-hardy crops
2027-04,Spring planting window begins; direct-sow warm crops
2027-05,Community opening event; planting window ends
2027-06,Produce swap wrap-up and final report to the funder
CSV
sed -i 's/- Timeline: not started\./- Timeline: done (`timeline.csv`)./' STATUS.md

cat > "$TRIAL_JOB_DIR/final-0.md" <<'MSG'
Added timeline.csv month by month (2026-09 to 2027-06). All three deliverables done; left the Next suggestions alone.
MSG
