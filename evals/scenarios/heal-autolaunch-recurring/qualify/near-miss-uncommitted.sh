# Reference behavior: the accepted outcome, except that the feature and its tests are left in the working tree. The
# heal itself is committed.
set -e
. "$TRIAL_SCENARIO_DIR/qualify/lib/steps.sh"
stale_command
implement since.patch
heal_and_close
report '`chorelog report --since YYYY-MM-DD` now counts only entries dated on or after that day, with tests and a line in the README; the suite passes. The feature is in the working tree and not committed.' 'Nothing else changed.'
