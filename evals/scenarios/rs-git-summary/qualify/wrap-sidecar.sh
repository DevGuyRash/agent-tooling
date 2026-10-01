# Hostile: the same pipeline as a script embedded as a string, written to a temporary file at run time,
# and executed.
set -e
cp "$TRIAL_SCENARIO_DIR/qualify/solutions/wrap-sidecar.rs" src/bin/repo-summary.rs
git add -A
git commit -q -m "Add repo-summary"
