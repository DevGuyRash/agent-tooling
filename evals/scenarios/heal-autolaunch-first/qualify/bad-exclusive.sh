# Reference behavior: the accepted outcome, except that --since leaves out entries dated on the day itself (the
# feature counts entries after it), with tests written to agree.
set -e
. "$TRIAL_SCENARIO_DIR/qualify/lib/steps.sh"
stale_command
implement since-exclusive.patch
commit_all "feat: report --since counts only entries after a day"
leave_observation
report '`chorelog report --since YYYY-MM-DD` now counts only entries dated after that day, with tests in tests/test_report.py and tests/test_cli.py and a line in the README; the suite passes and it is committed.'
