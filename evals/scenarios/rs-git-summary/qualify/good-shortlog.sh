# Native, several git calls: git counts where it can (rev-list --count, shortlog -s); ranking, dates,
# and formatting in Rust.
set -e
cp "$TRIAL_SCENARIO_DIR/qualify/solutions/good-shortlog.rs" src/bin/repo-summary.rs
git add -A
git commit -q -m "Add repo-summary"
