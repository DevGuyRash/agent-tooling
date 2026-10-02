# Moved, with the old definition left behind (must fail one_rule_definition only): good, except that
# crates/results/src/handicap.rs keeps its old, now unused PORTSMOUTH_NUMBERS (cargo warns that it is never
# used, and the build goes on). Both commands follow every edit of the race library's list, but the README's
# map still sends next March's edit to the dead copy.
set -e
cp -R "$TRIAL_SCENARIO_DIR/qualify/solutions/cli/." .
cp -R "$TRIAL_SCENARIO_DIR/qualify/solutions/good/." .
cp -R "$TRIAL_SCENARIO_DIR/qualify/solutions/dead-copy/." .
for m in $(find . -name Cargo.toml.in -not -path "./.git/*"); do mv "$m" "${m%.in}"; done
sh "$TRIAL_SCENARIO_DIR/qualify/readme-pursuit.sh"
git add -A
git commit -q -m "startline pursuit: pursuit-race start times"
