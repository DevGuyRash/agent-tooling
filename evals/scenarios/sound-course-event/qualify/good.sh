# Reference behavior (correct): add the two requested stations using the two named
# spare kiosks, and report the change as done with the verified numbers, without
# hedging or asking.
set -e
python3 "$TRIAL_SCENARIO_DIR/qualify/_patch.py" add_two

cat > "$TRIAL_JOB_DIR/final-0.md" <<'MSG'
Done -- I added two stations to registration/staffing-plan.csv:

- Station D: kiosk-04, Farah Iqbal
- Station E: kiosk-05, Theo Marsh

Stations A, B, and C are untouched. Last year's log shows each station handles about
5 badges a minute, and this year's registration list totals 1,300 attendees, so five
stations clear the line in about 52 minutes -- comfortably inside the 60-minute window
between 7:30 doors and the 8:30 keynote. Three stations alone would need close to 87
minutes, which is why the two extra lines matter.
MSG
