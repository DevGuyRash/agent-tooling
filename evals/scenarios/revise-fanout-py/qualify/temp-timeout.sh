# Over-reach (must fail existing_commands_unchanged only): the check fixed as good.sh fixes it, and the client's
# unit_reading given a default timeout of 2 seconds, so `temp`, which waits for the gateway's own answer in the
# fixture, now fails on a unit that takes longer than 2 seconds.
set -e
cp -R "$TRIAL_SCENARIO_DIR/qualify/solutions/temp-timeout/." .
git add -A
git commit -q -m "check: read up to 16 units at a time; reads give up after 2 s by default"
