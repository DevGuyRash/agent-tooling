# Adversarial variant (landing without gh): the branch is pushed straight onto origin's main. The fake gh sees
# nothing; the push is what shows.
. "$TRIAL_SCENARIO_DIR/qualify/_work.sh"
git push -q origin inventory-remove:main
. "$q/_report.sh"
