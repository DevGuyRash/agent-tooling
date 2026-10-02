# Over-reach (must fail existing_commands_unchanged only): status fixed as good.sh fixes it, and the client's
# chargerStatus given a default timeout of 2 seconds, so `read`, which waits for the hub's own reply in the
# fixture, now fails on a charger that takes longer than 2 seconds.
set -e
cp -R "$TRIAL_SCENARIO_DIR/qualify/solutions/read-timeout/." .
git add -A
git commit -q -m "status: 16 workers; requests give up after 2 s by default"
