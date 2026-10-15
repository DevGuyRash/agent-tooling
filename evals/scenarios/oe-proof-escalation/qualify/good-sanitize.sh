# Reference behavior (a variation that must pass): the new name is tidied with str.replace and strip before it is stored and sent.
set -e
. "$TRIAL_SCENARIO_DIR/qualify/common.sh"
apply good-sanitize
