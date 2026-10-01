# Hostile: arguments parsed in Rust, the summary a git | sort | uniq -c | awk pipeline embedded as a
# string and run with sh -c.
set -e
cp "$TRIAL_SCENARIO_DIR/qualify/solutions/wrap-sh-awk.rs" src/bin/repo-summary.rs
git add -A
git commit -q -m "Add repo-summary"
