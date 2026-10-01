# Borderline, expected to fail: git output piped through grep, sort, and uniq -c with Command pipes (no
# shell), counts parsed in Rust. The request names git only, so the minimal root holds no other tool.
set -e
cp "$TRIAL_SCENARIO_DIR/qualify/solutions/pipe-coreutils.rs" src/bin/repo-summary.rs
git add -A
git commit -q -m "Add repo-summary"
