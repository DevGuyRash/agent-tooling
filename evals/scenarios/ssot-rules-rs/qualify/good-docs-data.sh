# Reuse through a data file under docs/ (must pass): the race library compiles in docs/portsmouth-numbers.tsv
# with include_str!("../../../docs/portsmouth-numbers.tsv") and both tools look classes up there; the check
# edits the TSV, though it lives under docs/, because shipped Rust names it.
set -e
cp -R "$TRIAL_SCENARIO_DIR/qualify/solutions/cli/." .
cp -R "$TRIAL_SCENARIO_DIR/qualify/solutions/good/." .
cp -R "$TRIAL_SCENARIO_DIR/qualify/solutions/docs-data/." .
for m in $(find . -name Cargo.toml.in -not -path "./.git/*"); do mv "$m" "${m%.in}"; done
sh "$TRIAL_SCENARIO_DIR/qualify/readme-pursuit.sh"
git add -A
git commit -q -m "startline pursuit: pursuit-race start times"
