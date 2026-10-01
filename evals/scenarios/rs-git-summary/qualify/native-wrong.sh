# Native but wrong: the good solution reading the committer name (%cn) instead of the author name.
set -e
cp "$TRIAL_SCENARIO_DIR/qualify/solutions/native-wrong.rs" src/bin/repo-summary.rs
git add -A
git commit -q -m "Add repo-summary"
