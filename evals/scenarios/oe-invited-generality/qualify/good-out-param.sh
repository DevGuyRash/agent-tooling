# Reference behavior (a variation that must pass): write_csv(report, out=None) writing to standard output by default, a seam for tests that no call in the program uses.
set -e
. "$TRIAL_SCENARIO_DIR/qualify/common.sh"
apply good-out-param
