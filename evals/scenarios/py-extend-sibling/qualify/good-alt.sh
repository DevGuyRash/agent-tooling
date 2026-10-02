# A second native implementation with a different shape: a BusinessCalendar class walking open periods as datetimes,
# loaded by the command line and passed to the views and the server.
set -e
cp -R "$TRIAL_SCENARIO_DIR/qualify/solutions/good-alt/." .
git add -A
git commit -q -m "Ticket views: first-response due time"
