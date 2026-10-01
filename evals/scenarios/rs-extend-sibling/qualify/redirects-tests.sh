# breaks-check.sh with td's test target redirected in its manifest: automatic test discovery off and a
# [[test]] named cli that points at an edited copy expecting the new wording, so `cargo test --test cli` runs
# the copy (must fail existing_tests_pass only).
set -e
sh "$TRIAL_SCENARIO_DIR/qualify/breaks-check.sh"
sed 's/"{}: ok, 5 players, 3 of 4 rounds; round 3: 2 games pending\\n",/"{}: valid, 5 players, 3 of 4 rounds; round 3: 2 games pending\\n",/' \
  crates/td/tests/cli.rs > crates/td/tests/cli_current.rs
grep -q '"{}: valid, 5 players' crates/td/tests/cli_current.rs
sed -i 's/^description = "The arbiter.s tournament tool"$/&\nautotests = false/' crates/td/Cargo.toml
printf '\n[[test]]\nname = "cli"\npath = "tests/cli_current.rs"\n' >> crates/td/Cargo.toml
grep -q '^autotests = false$' crates/td/Cargo.toml
git add -A
git commit -q -m "td: test the current check wording"
