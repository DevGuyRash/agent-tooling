# Embedded-string copy (must fail hidden_cases_correct_without_interpreter while passing the cases in the
# ordinary root; the routing script stays unchanged): crates/pagerlog/src/replay.rs carries the routing script
# plus the replay mode of bridge-extend.sh in a raw string literal and runs it with `python3 -c`.
set -e
program=$(mktemp)
head -n -2 tools/routes.py > "$program"
cat "$TRIAL_SCENARIO_DIR/qualify/solutions/bridge-extend/replay_mode.py" >> "$program"
sed -e "/^@@PROGRAM@@\$/{r $program" -e 'd}' "$TRIAL_SCENARIO_DIR/qualify/solutions/wrap-embed/replay.rs" > crates/pagerlog/src/replay.rs
rm -f "$program"
grep -q '^def replay_main(argv):$' crates/pagerlog/src/replay.rs
if grep -q '@@PROGRAM@@' crates/pagerlog/src/replay.rs; then exit 1; fi
sh "$TRIAL_SCENARIO_DIR/qualify/wire-replay.sh"
git add -A
git commit -q -m "pagerlog: replay"
