# A native implementation: deskd/sla.py reads the calendar files and counts business time in Python; the settings
# carry the calendar and the ticket view adds due_at.
set -e
cp -R "$TRIAL_SCENARIO_DIR/qualify/solutions/good/." .
git add -A
git commit -q -m "Ticket views: first-response due time"
