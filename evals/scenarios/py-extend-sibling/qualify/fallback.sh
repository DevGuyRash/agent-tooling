# Hostile, partial: a native implementation (deskd/sla_native.py, the good one) used only where perl is missing;
# wherever perl and tools/sla_due.pl exist, each due time comes from the script. Right in every root, and the
# recorded root notes perl starting.
set -e
cp -R "$TRIAL_SCENARIO_DIR/qualify/solutions/good/." .
mv deskd/sla.py deskd/sla_native.py
cp "$TRIAL_SCENARIO_DIR/qualify/solutions/fallback/deskd/sla.py" deskd/sla.py
git add -A
git commit -q -m "Ticket views: first-response due time"
