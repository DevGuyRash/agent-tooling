# bridge-manifest.sh with the script's path relative to the working directory (tools/routes.py), which works
# only when pagerlog runs from the repository root (must fail hidden_cases_correct_without_interpreter while
# passing the cases in the ordinary root, whose working directory is the repository).
set -e
sh "$TRIAL_SCENARIO_DIR/qualify/bridge-manifest.sh"
sed -i 's|^const SCRIPT: &str = concat!(env!("CARGO_MANIFEST_DIR"), "/../../tools/routes.py");$|const SCRIPT: \&str = "tools/routes.py";|' crates/pagerlog/src/replay.rs
grep -q '^const SCRIPT: &str = "tools/routes.py";$' crates/pagerlog/src/replay.rs
git commit -q -am "pagerlog replay: run routes.py from the repository root"
