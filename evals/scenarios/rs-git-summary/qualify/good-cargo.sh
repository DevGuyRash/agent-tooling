# The good solution, built and tested with cargo inside the confined run first, the way an agent would.
# Its arm lists the Rust toolchain in "readable"; without that, the rustup proxies on PATH cannot choose a
# toolchain, cargo fails, and this run is invalid rather than passing.
set -e
cp "$TRIAL_SCENARIO_DIR/qualify/solutions/good.rs" src/bin/repo-summary.rs
cargo test --offline --quiet
git add -A
git commit -q -m "Add repo-summary"
