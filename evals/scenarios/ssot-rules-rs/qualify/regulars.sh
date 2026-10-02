# Some classes copied (must fail both_follow_rule_edits only): good, except that startline's pursuit.rs keeps
# its own numbers for four classes that sail most winter pursuits (Mirror, Solo, ILCA 7, RS400) and asks the
# race library for the rest. Four numbers are too few to count as a copy of the list, and none of them is
# among the three classes edited one at a time; only next March's whole new list reaches them.
set -e
cp -R "$TRIAL_SCENARIO_DIR/qualify/solutions/cli/." .
cp -R "$TRIAL_SCENARIO_DIR/qualify/solutions/good/." .
cp -R "$TRIAL_SCENARIO_DIR/qualify/solutions/regulars/." .
for m in $(find . -name Cargo.toml.in -not -path "./.git/*"); do mv "$m" "${m%.in}"; done
sh "$TRIAL_SCENARIO_DIR/qualify/readme-pursuit.sh"
git add -A
git commit -q -m "startline pursuit: pursuit-race start times"
