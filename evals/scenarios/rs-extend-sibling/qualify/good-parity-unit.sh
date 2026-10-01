# Native plus a parity oracle inside the module (must pass): good.sh, with a #[cfg(test)] module in
# crates/td/src/standings.rs that runs the website script with python3 on a finished tournament and compares
# its numbers with td's. The check's static measures leave #[cfg(test)] items out of the shipped code.
set -e
sh "$TRIAL_SCENARIO_DIR/qualify/good.sh"
cat "$TRIAL_SCENARIO_DIR/qualify/solutions/parity_unit.rs" >> crates/td/src/standings.rs
git commit -q -am "td standings: compare with the website script in a unit test"
