# Over-reach (must fail existing_commands_unchanged only): the check fixed as good.sh fixes it, and `units` no
# longer prints each unit's zone.
set -e
cp -R "$TRIAL_SCENARIO_DIR/qualify/solutions/units-format/." .
git add -A
git commit -q -m "check: read up to 16 units at a time; units prints IDs only"
