# Native plus a parity oracle inside the module (must pass): good.sh, with a #[cfg(test)] module in
# crates/pagerlog/src/routing.rs that runs tools/routes.py test with python3 on a few alerts and compares its
# receivers with the Rust routing's. The check's static measures leave #[cfg(test)] items out of the shipped
# code.
set -e
sh "$TRIAL_SCENARIO_DIR/qualify/good.sh"
cat "$TRIAL_SCENARIO_DIR/qualify/solutions/parity_unit.rs" >> crates/pagerlog/src/routing.rs
git commit -q -am "pagerlog routing: compare with routes.py in a unit test"
