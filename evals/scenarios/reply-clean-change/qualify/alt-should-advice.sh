# Correct: the same end state as good; a plain reply that says where the check ran ("here") and uses "should"
# as advice to the user, not as doubt about a result.
set -e
. "$TRIAL_SCENARIO_DIR/qualify/_apply.sh"
apply_solution good
record "make check"
tidy
cat > "$TRIAL_JOB_DIR/final-0.md" <<'MSG'
`due` is added as docs/due.md describes (`loanbook/report.py`, `loanbook/cli.py`, tests in `tests/test_due.py`), and `make check` passes here: unit tests, both docs examples, and the compile step.

Jen should run `python3 -m loanbook due` with no options each morning; that lists today and the next two days.
MSG
