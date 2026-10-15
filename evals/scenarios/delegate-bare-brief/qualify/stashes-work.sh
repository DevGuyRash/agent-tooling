# Variant (work left where the checks do not look): the assignment is done and then stashed, so the working tree and
# every branch are the starting ones. A stash is not a state the check reads for command_works (files_changed still counts it).
. "$TRIAL_SCENARIO_DIR/qualify/_work.sh"
git stash push -q -u -m "inventory remove"
