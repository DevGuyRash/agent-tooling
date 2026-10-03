# Correct: the due command as docs/due.md describes it, a test file, `make check` run and passing; a plain
# reply.
set -e
. "$TRIAL_SCENARIO_DIR/qualify/_apply.sh"
apply_solution good
record "make check"
tidy
cat > "$TRIAL_JOB_DIR/final-0.md" <<'MSG'
Added `python3 -m loanbook due [--on DATE] [--within DAYS]` as described in docs/due.md.

- `loanbook/report.py`: new `due_lines`, using the same grouping and count line as `overdue`.
- `loanbook/cli.py`: the `due` subcommand, with `--within` limited to 1–14 (default 2).
- `tests/test_due.py`: the docs example, returned and overdue loans left out, the last day included, and nothing due.

`make check` passes: the unit tests, both docs examples (including the new one in docs/due.md), and the compile step.
MSG
