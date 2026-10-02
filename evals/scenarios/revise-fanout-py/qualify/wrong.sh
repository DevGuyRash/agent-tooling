# Wrong (must fail answered_units_correct only): good.sh's pool of 16, but each unit's line printed as soon as
# its read finishes, so the lines come out in completion order instead of ID order. The summary is right.
set -e
cp -R "$TRIAL_SCENARIO_DIR/qualify/solutions/wrong/." .
git add -A
git commit -q -m "check: print units as they are read"
