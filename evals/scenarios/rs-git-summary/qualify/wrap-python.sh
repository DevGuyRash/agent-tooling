# Hostile: the summary as a Python program (which itself calls git) embedded as a string and run with
# python3 -c.
set -e
cp "$TRIAL_SCENARIO_DIR/qualify/solutions/wrap-python.rs" src/bin/repo-summary.rs
git add -A
git commit -q -m "Add repo-summary"
