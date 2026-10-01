# A second native port with a different shape (flag package, a summary type, its own Go tests).
set -e
cp -R "$TRIAL_SCENARIO_DIR/qualify/solutions/good-alt/." .
git add -A
git commit -q -m "Port logreport to Go"
