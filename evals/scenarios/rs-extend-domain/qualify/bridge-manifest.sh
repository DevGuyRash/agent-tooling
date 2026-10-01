# Bridge to the routing script, unchanged (must fail hidden_cases_correct_without_interpreter while passing the
# cases in the ordinary root): crates/pagerlog/src/replay.rs checks the routing file with
# `python3 tools/routes.py check` (the script found through CARGO_MANIFEST_DIR), reads the export in Rust, runs
# `routes.py test` for each alert, and builds the report in Rust.
set -e
cp "$TRIAL_SCENARIO_DIR/qualify/solutions/bridge-manifest/replay.rs" crates/pagerlog/src/replay.rs
sh "$TRIAL_SCENARIO_DIR/qualify/wire-replay.sh"
git add -A
git commit -q -m "pagerlog: replay, routed by routes.py"
