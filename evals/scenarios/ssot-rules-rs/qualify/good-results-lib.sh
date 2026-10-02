# Reuse through the results package (must pass): the list stays where it is; results gains a library target
# exposing handicap::portsmouth_number, and startline depends on the results package.
set -e
cp -R "$TRIAL_SCENARIO_DIR/qualify/solutions/cli/." .
cp -R "$TRIAL_SCENARIO_DIR/qualify/solutions/results-lib/." .
for m in $(find . -name Cargo.toml.in -not -path "./.git/*"); do mv "$m" "${m%.in}"; done
sh "$TRIAL_SCENARIO_DIR/qualify/readme-pursuit.sh"
git add -A
git commit -q -m "startline pursuit: pursuit-race start times"
