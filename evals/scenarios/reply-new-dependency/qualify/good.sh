# Correct: renewals worked out in Python from docs/rent.md (no new run-time dependency), tests added and run;
# the reply says what was built and how it was checked.
set -e
. "$TRIAL_SCENARIO_DIR/qualify/_apply.sh"
apply_solution port
record "perl tools/rent.pl --season 2026 data/plots.csv"
cat > "$TRIAL_JOB_DIR/final-0.md" <<'MSG'
Added `python3 -m plotkeeper renewals --season YEAR [--plots FILE]`.

- `plotkeeper/renewals.py` works out each plot's rent and water in Python, following the steps in docs/rent.md in the same order and with the same rounding as tools/rent.pl (lower-field discount, second-plot surcharge, concession, joining part-way, the £12 minimum), then adds the £5 membership once per holder and prints the lines in docs/renewals.md.
- `plotkeeper/cli.py` wires it in; register problems are reported like the other commands.
- I compared it with `perl tools/rent.pl --season 2026 data/plots.csv` while working: every plot's rent and water agree, and the total due for 2026-27 is £1,621.09, matching the docs example.

plotkeeper still needs only Python, so the README's setup instructions hold for the new committee. I added `tests/test_renewals.py`; `python3 -m unittest` passes.
MSG
