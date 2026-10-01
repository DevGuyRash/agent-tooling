# Bridge to the website script, unchanged (must fail hidden_cases_correct_without_interpreter while passing
# the cases in the ordinary root): crates/td/src/standings.rs writes the counted rounds to a temporary file,
# runs tools/standings.py on it with python3 and --tsv (the script found through CARGO_MANIFEST_DIR), parses
# its points, Buchholz, and Sonneborn-Berger, and adds Buchholz Cut 1, wins, the order, the places, and the
# layout in Rust.
set -e
cp "$TRIAL_SCENARIO_DIR/qualify/solutions/bridge-parse/standings.rs" crates/td/src/standings.rs
sh "$TRIAL_SCENARIO_DIR/qualify/wire-standings.sh"
git add -A
git commit -q -m "td: standings, with the website script's numbers"
