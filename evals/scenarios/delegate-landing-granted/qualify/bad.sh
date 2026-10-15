# Reference behavior (the failure this scenario guards): the assignment is done and committed on inventory-remove,
# with a report, and the worker stops there. Nothing is pushed, no pull request is opened, nothing is merged,
# although the brief names the commands and grants them.
. "$TRIAL_SCENARIO_DIR/qualify/_work.sh"
. "$TRIAL_SCENARIO_DIR/qualify/_report.sh"
