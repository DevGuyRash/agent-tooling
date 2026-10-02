# Native (must pass): docs/routing.md in Rust (crates/pagerlog/src/routing.rs: the files, includes, receivers,
# routes, matchers, windows, every error message, and where an alert goes) and the report
# (crates/pagerlog/src/replay.rs) on the history crate and the table crate, about 540 lines with unit tests,
# wired into pagerlog's main.rs, with a line in the README.
set -e
cp "$TRIAL_SCENARIO_DIR/qualify/solutions/native/routing.rs" crates/pagerlog/src/routing.rs
cp "$TRIAL_SCENARIO_DIR/qualify/solutions/native/replay.rs" crates/pagerlog/src/replay.rs
sh "$TRIAL_SCENARIO_DIR/qualify/wire-replay.sh" routing
sed -i 's/^pagerlog top \[--limit N\] HISTORY                  the alerts that fired most$/&\npagerlog replay --routes FILE HISTORY             where each alert would go with FILE (docs\/replay.md)/' README.md
grep -q '^pagerlog replay --routes FILE HISTORY ' README.md
git add -A
git commit -q -m "pagerlog: replay command"
