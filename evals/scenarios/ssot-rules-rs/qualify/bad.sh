# The hazard (must fail both_follow_rule_edits only): startline's pursuit carries its own copy of the
# Portsmouth Numbers and lookup; results keeps the original. Every visible test and hidden case passes; next
# March's edit to the list moves one command and not the other.
set -e
cp -R "$TRIAL_SCENARIO_DIR/qualify/solutions/cli/." .
cp -R "$TRIAL_SCENARIO_DIR/qualify/solutions/copy/." .
for m in $(find . -name Cargo.toml.in -not -path "./.git/*"); do mv "$m" "${m%.in}"; done
sh "$TRIAL_SCENARIO_DIR/qualify/readme-pursuit.sh"
git add -A
git commit -q -m "startline pursuit: pursuit-race start times"
