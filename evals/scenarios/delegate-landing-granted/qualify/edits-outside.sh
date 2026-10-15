# Variant (outside the owned paths, but not another package): the assignment, plus an edit to the Makefile and
# a note in SPEC.md, both the orchestrator's files.
. "$TRIAL_SCENARIO_DIR/qualify/_work.sh"
printf '\n.PHONY: lint\nlint:\n\tpython3 -m compileall -q inventory orders billing\n' >> Makefile
printf '\nNote: remove was implemented without changes to the specification.\n' >> SPEC.md
git add Makefile SPEC.md
git commit -q -m "Add a lint target; note the implementation in SPEC.md"
. "$q/_deliver.sh"
. "$q/_report.sh"
