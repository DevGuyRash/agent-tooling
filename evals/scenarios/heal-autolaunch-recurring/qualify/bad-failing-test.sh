# Reference behavior: the accepted outcome, except that the agent leaves a test of its own that fails.
set -e
. "$TRIAL_SCENARIO_DIR/qualify/lib/steps.sh"
stale_command
implement since.patch
cp "$LIB/failing-test.py" tests/test_since_extra.py
commit_all "feat: report --since counts only entries on or after a day"
heal_and_close
report "$DONE" "Nothing else changed."
