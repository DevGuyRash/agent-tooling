# Near-miss (should fail): attempts the right deliverable but the content falls well short
# of what was asked — only two months, no planting window or opening event marked.
set -e

cat > timeline.csv <<'CSV'
Month,Milestone
September,Kickoff
June,Final report
CSV

cat > "$TRIAL_JOB_DIR/final-0.md" <<'MSG'
Added a timeline.csv with the kickoff and final report dates.
MSG
