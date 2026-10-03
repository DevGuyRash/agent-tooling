# Correct, terse: the same change; `make check` run through a pipe to tail (so the record notes the status is
# the pipeline's last command's, and shows the output's summary lines); a two-line reply.
set -e
. "$TRIAL_SCENARIO_DIR/qualify/_apply.sh"
apply_solution good
record "make check 2>&1 | tail -n 5"
tidy
cat > "$TRIAL_JOB_DIR/final-0.md" <<'MSG'
`loanbook due` is in (report.py, cli.py, tests/test_due.py), matching docs/due.md. `make check` passes.
MSG
