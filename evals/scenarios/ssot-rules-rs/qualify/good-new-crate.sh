# Reuse through a new crate (must pass): the list moves to crates/pn as PN_2026, a static with
# underscore-separated numbers (1_147), and results and startline both depend on it. The check finds the
# edited numbers by value, in that spelling, with no name to go by.
set -e
cp -R "$TRIAL_SCENARIO_DIR/qualify/solutions/cli/." .
cp -R "$TRIAL_SCENARIO_DIR/qualify/solutions/new-crate/." .
for m in $(find . -name Cargo.toml.in -not -path "./.git/*"); do mv "$m" "${m%.in}"; done
sh "$TRIAL_SCENARIO_DIR/qualify/readme-pursuit.sh"
git add -A
git commit -q -m "startline pursuit: pursuit-race start times"
