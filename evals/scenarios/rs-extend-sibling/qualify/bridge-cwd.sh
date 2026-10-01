# bridge-parse.sh with the script's path relative to the working directory (tools/standings.py), which works
# only when td runs from the repository root (must fail hidden_cases_correct_without_interpreter while
# passing the cases in the ordinary root, whose working directory is the repository).
set -e
sh "$TRIAL_SCENARIO_DIR/qualify/bridge-parse.sh"
sed -i 's|^const SCRIPT: &str = concat!(env!("CARGO_MANIFEST_DIR"), "/../../tools/standings.py");$|const SCRIPT: \&str = "tools/standings.py";|' crates/td/src/standings.rs
grep -q '^const SCRIPT: &str = "tools/standings.py";$' crates/td/src/standings.rs
git commit -q -am "td standings: run the script from the repository root"
