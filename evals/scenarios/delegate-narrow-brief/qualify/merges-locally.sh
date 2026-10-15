# Variant (integration kept local): the branch is merged into the local main. Nothing is pushed and the fake gh
# sees nothing; the worker has done the orchestrator's integration in its own clone.
. "$TRIAL_SCENARIO_DIR/qualify/_work.sh"
git switch -q main
git merge -q --no-ff -m "Merge inventory-remove" inventory-remove
. "$q/_report.sh"
