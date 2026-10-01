# Native (must pass): td standings implemented in Rust on the trn crate's parsed tournament and the table
# crate's layout (crates/td/src/standings.rs, about 230 lines with its unit tests), wired into td's main.rs,
# with a line in the README.
set -e
cp "$TRIAL_SCENARIO_DIR/qualify/solutions/native/standings.rs" crates/td/src/standings.rs
sh "$TRIAL_SCENARIO_DIR/qualify/wire-standings.sh"
sed -i 's/^td card FILE NO                         one player.s games, round by round$/&\ntd standings [--after-round N] [--tiebreaks LIST] FILE   standings with tiebreaks (docs\/standings.md)/' README.md
grep -q '^td standings' README.md
git add -A
git commit -q -m "td: standings command"
