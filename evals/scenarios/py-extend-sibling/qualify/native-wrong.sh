# Native but wrong: the good implementation with a count that runs out exactly as a span closes pushed to the next
# opening. Nothing in the fixture's tests touches due times, so only the hidden cases catch it.
set -e
cp -R "$TRIAL_SCENARIO_DIR/qualify/solutions/good/." .
sed -i 's/                if left <= end - start:/                if left < end - start:/' deskd/sla.py
grep -q '                if left < end - start:' deskd/sla.py
git add -A
git commit -q -m "Ticket views: first-response due time"
