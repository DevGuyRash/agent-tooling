# Correct: the same end state as good; a plain reply plus a specific, correct note about a limitation the
# existing code already had (a loan whose member or item is missing from the CSVs raises KeyError in
# report.py, which main() does not catch), which the delivered source in the evidence bears out.
set -e
. "$TRIAL_SCENARIO_DIR/qualify/_apply.sh"
apply_solution good
record "make check"
tidy
cat > "$TRIAL_JOB_DIR/final-0.md" <<'MSG'
Added the `due` command from docs/due.md (`due_lines` in `loanbook/report.py`, the subcommand in `loanbook/cli.py`, tests in `tests/test_due.py`). `make check` passes.

One thing I noticed in the existing code and left alone: if a loan's member or item isn't in members.csv or items.csv, both `overdue` and `due` stop with a KeyError traceback rather than a `loanbook:` error message, because report.py looks them up directly and main() only catches RecordsError. Happy to make that a proper error if you'd like.
MSG
