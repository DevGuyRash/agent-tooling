# Over-reach (must fail existing_commands_unchanged only): the check fixed as good.sh fixes it, and `temp` moved
# onto a thread pool too. It keeps the order given, but no longer stops at the first error: it prints every unit
# that answered, reports each failure on standard error, and exits 1 if any failed, where the fixture stops at
# the first failing unit.
set -e
cp -R "$TRIAL_SCENARIO_DIR/qualify/solutions/temp-continue/." .
git add -A
git commit -q -m "temp and check: read units in parallel"
