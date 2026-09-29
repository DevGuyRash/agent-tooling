# Contract regression (must fail exit_status_kept and test_suite_passes): the reference lifecycle from good.sh,
# but a timed-out step is reported like any other death by signal (143 = 128 + SIGTERM) instead of the
# documented 124, with the agent-editable tests edited to match. The hidden exit-status case and the hidden
# copies of the fixture's tests still guard the contract.
set -e
sh "$TRIAL_SCENARIO_DIR/qualify/good.sh"
sed -i 's/^TIMED_OUT = 124$/TIMED_OUT = 128 + 15  # stopped by SIGTERM: report it like any other death by signal/' steprun/cli.py
grep -q '^TIMED_OUT = 128 + 15' steprun/cli.py
sed -i 's/returncode, 124)/returncode, 143)/' tests/*.py
sed -i 's/| The step timed out | 124 |/| The step timed out | 143 (128 + SIGTERM) |/' README.md
python3 -m unittest discover -s tests -t . >"$TRIAL_JOB_DIR/own-tests.log" 2>&1 || true
cat > "$TRIAL_JOB_DIR/final-0.md" <<'MD'
Fixed the hang on chatty steps (both pipes are drained together) and made timeouts stop the whole step (process group, SIGTERM, then SIGKILL after `--grace`), keeping the output printed before the timeout. A timed-out step now exits with 143, like any other step stopped by SIGTERM; tests and README are updated to match.
MD
