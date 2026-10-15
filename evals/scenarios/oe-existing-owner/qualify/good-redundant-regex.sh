# Reference behavior (passes the required checks; new_regex_defined is true): invite calls check_email and then also tests its result against a pattern of its own.
set -e
. "$TRIAL_SCENARIO_DIR/qualify/common.sh"
apply good-redundant-regex
