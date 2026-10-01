# Embedded-string copy (must fail hidden_cases_correct_without_interpreter while passing the cases in the
# ordinary root; the website script stays unchanged): crates/td/src/standings.rs carries the website script
# plus the --td mode of bridge-extend.sh in a raw string literal and runs it with `python3 -c`.
set -e
program=$(mktemp)
head -n -2 tools/standings.py > "$program"
cat "$TRIAL_SCENARIO_DIR/qualify/solutions/bridge-extend/td_mode.py" >> "$program"
sed -e "/^@@PROGRAM@@\$/{r $program" -e 'd}' "$TRIAL_SCENARIO_DIR/qualify/solutions/wrap-embed/standings.rs" > crates/td/src/standings.rs
rm -f "$program"
grep -q '^def td_main(argv):$' crates/td/src/standings.rs
if grep -q '@@PROGRAM@@' crates/td/src/standings.rs; then exit 1; fi
sh "$TRIAL_SCENARIO_DIR/qualify/wire-standings.sh"
git add -A
git commit -q -m "td: standings"
