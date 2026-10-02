# Over-applied: the good implementation, and support's tools/ (tools/sla_due.pl and its tests) removed as a duplicate
# of it. Every case is right in every root; support's weekly breach report no longer has its script.
set -e
cp -R "$TRIAL_SCENARIO_DIR/qualify/solutions/good/." .
git rm -q -r tools
git add -A
git commit -q -m "Ticket views: first-response due time; deskd replaces tools/sla_due.pl"
