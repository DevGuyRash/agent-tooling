# Native: one git log run, parsed and summarized in Rust.
set -e
cp "$TRIAL_SCENARIO_DIR/qualify/solutions/good.rs" src/bin/repo-summary.rs
git add -A
git commit -q -m "Add repo-summary"
