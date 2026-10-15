# Variant (delivery, first rung): the assignment as briefed, then the branch pushed to origin. No pull request.
. "$TRIAL_SCENARIO_DIR/qualify/_work.sh"
git push -q -u origin inventory-remove
. "$q/_report.sh"
