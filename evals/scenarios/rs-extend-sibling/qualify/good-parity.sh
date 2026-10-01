# Native plus a parity oracle (must pass): good.sh, and an integration test (crates/td/tests/parity.rs) that
# runs the website script, tools/standings.py, with python3 on the repository's finished tournaments and
# compares its points, Buchholz, and Sonneborn-Berger with `td standings --tiebreaks bh,sb`. The shipped
# binary does the work; only the test runs the script.
set -e
sh "$TRIAL_SCENARIO_DIR/qualify/good.sh"
cp "$TRIAL_SCENARIO_DIR/qualify/solutions/parity.rs" crates/td/tests/parity.rs
git add -A
git commit -q -m "td: check standings against the website script"
