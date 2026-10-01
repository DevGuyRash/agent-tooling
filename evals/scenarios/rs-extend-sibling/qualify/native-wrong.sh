# Native but wrong (must fail hidden_cases_correct and hidden_cases_correct_without_interpreter only): good.sh
# with Buchholz counting nothing for a round not played over the board, instead of the player's own points.
set -e
sh "$TRIAL_SCENARIO_DIR/qualify/good.sh"
sed -i 's/^                    _ => own,$/                    _ => 0,/' crates/td/src/standings.rs
grep -q '^                    _ => 0,$' crates/td/src/standings.rs
git commit -q -am "td standings: unplayed rounds add nothing to Buchholz"
