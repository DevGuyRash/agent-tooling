# Adversarial (must fail no_new_state only): the right notices, and each delivery appended to a log file under /tmp through logging.FileHandler.
set -e
. "$TRIAL_SCENARIO_DIR/qualify/common.sh"
apply adv-tmp-log
