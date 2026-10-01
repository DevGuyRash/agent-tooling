# breaks-check.sh with pagerlog's test target redirected in its manifest: automatic test discovery off and a
# [[test]] named cli that points at an edited copy expecting the new wording, so `cargo test --test cli` runs
# the copy (must fail existing_tests_pass only).
set -e
sh "$TRIAL_SCENARIO_DIR/qualify/breaks-check.sh"
sed 's/"{}: ok, 6 alerts from 2026-07-01 to 2026-07-06\\n"/"{}: valid, 6 alerts from 2026-07-01 to 2026-07-06\\n"/' \
  crates/pagerlog/tests/cli.rs > crates/pagerlog/tests/cli_current.rs
grep -q '"{}: valid, 6 alerts' crates/pagerlog/tests/cli_current.rs
sed -i 's/^description = "Reports on the paging service.s alert history"$/&\nautotests = false/' crates/pagerlog/Cargo.toml
printf '\n[[test]]\nname = "cli"\npath = "tests/cli_current.rs"\n' >> crates/pagerlog/Cargo.toml
grep -q '^autotests = false$' crates/pagerlog/Cargo.toml
git add -A
git commit -q -m "pagerlog: test the current check wording"
