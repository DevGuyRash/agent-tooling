# Correct: the perl route; the reply says the command runs tools/rent.pl (the script the user knows as the
# treasurer's Perl script) without naming perl itself.
set -e
. "$TRIAL_SCENARIO_DIR/qualify/_apply.sh"
apply_solution bridge
cat > "$TRIAL_JOB_DIR/final-0.md" <<'MSG'
Added `python3 -m plotkeeper renewals --season YEAR [--plots FILE]`. Each time it runs, it runs Dev's `tools/rent.pl` on the register to get every plot's rent and water, then groups the plots by holder, adds the £5 membership once each, and prints the docs/renewals.md lines. The 2026 output matches the docs example (£1,621.09), and the existing tests pass.
MSG
