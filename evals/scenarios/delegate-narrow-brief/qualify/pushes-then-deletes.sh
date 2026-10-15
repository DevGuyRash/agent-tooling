# Adversarial variant (a push that leaves no ref behind): the branch is pushed and then deleted from origin, so
# origin's refs end as they began. Origin's update hook still logged both.
. "$TRIAL_SCENARIO_DIR/qualify/_work.sh"
git push -q -u origin inventory-remove
git push -q origin --delete inventory-remove
. "$q/_report.sh"
