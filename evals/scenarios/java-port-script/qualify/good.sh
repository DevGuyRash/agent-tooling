# A native Java port: options, input parsing, validation, tallying, sorting, and the table in one class.
set -e
cp -R "$TRIAL_SCENARIO_DIR/qualify/solutions/good/." .
git add -A
git commit -q -m "Port runner-usage to Java"
