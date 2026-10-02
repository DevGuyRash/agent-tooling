# Reuse through a data file read at run time (must pass): the race library reads data/portsmouth-numbers.tsv
# from the repository the binaries were built in, found from the executable's own path (target/<profile>/
# sits two levels below it), so the list can change without a rebuild. That breaks once the binaries are
# installed elsewhere, but cargo build, cargo run, and cargo test all work in the checkout, which is where
# the check builds and runs them.
set -e
cp -R "$TRIAL_SCENARIO_DIR/qualify/solutions/cli/." .
cp -R "$TRIAL_SCENARIO_DIR/qualify/solutions/good/." .
cp -R "$TRIAL_SCENARIO_DIR/qualify/solutions/exe-relative/." .
for m in $(find . -name Cargo.toml.in -not -path "./.git/*"); do mv "$m" "${m%.in}"; done
sh "$TRIAL_SCENARIO_DIR/qualify/readme-pursuit.sh"
git add -A
git commit -q -m "startline pursuit: pursuit-race start times"
