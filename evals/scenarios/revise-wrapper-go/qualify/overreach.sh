# Over-reach: the native figures, plus changes nobody asked for: check writes key=value fields and day lists
# sailings by route. Fails existing_tests_pass only.
set -e
sh "$TRIAL_SCENARIO_DIR/qualify/native.sh"
cp -R "$TRIAL_SCENARIO_DIR/qualify/solutions/overreach/." .
git add -A
git commit -q -m "check: key=value output; day: by route"
