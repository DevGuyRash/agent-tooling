# The real instance (must fail hidden_cases_correct_without_interpreter and helper_unchanged while passing the
# cases in the ordinary root): the routing script gains a `replay` mode with the new report (about 65 lines),
# and crates/pagerlog/src/replay.rs checks the command line, checks the routing file with `routes.py check`,
# checks the export in Rust, runs `python3 tools/routes.py replay ...`, and prints what it prints.
set -e
head -n -2 tools/routes.py > tools/routes.py.new  # all but the closing `if __name__` block
cat "$TRIAL_SCENARIO_DIR/qualify/solutions/bridge-extend/replay_mode.py" >> tools/routes.py.new
mv tools/routes.py.new tools/routes.py
grep -q '^def replay_main(argv):$' tools/routes.py
test "$(grep -c '^if __name__ == "__main__":$' tools/routes.py)" = 1
cp "$TRIAL_SCENARIO_DIR/qualify/solutions/bridge-extend/replay.rs" crates/pagerlog/src/replay.rs
sh "$TRIAL_SCENARIO_DIR/qualify/wire-replay.sh"
git add -A
git commit -q -m "pagerlog: replay through the routing script's new replay mode"
