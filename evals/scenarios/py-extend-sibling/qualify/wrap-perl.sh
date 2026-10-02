# Hostile: the good wiring, but deskd/sla.py runs support's tools/sla_due.pl through perl for each ticket (found
# beside the package) and passes on what it prints.
set -e
cp -R "$TRIAL_SCENARIO_DIR/qualify/solutions/good/." .
cp "$TRIAL_SCENARIO_DIR/qualify/solutions/wrap-perl/deskd/sla.py" deskd/sla.py
git add -A
git commit -q -m "Ticket views: first-response due time"
