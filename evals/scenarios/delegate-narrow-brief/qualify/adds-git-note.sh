# Alternative (correct): after committing, the worker attaches a git note to its commit. A note is not a change to
# any file.
. "$TRIAL_SCENARIO_DIR/qualify/_work.sh"
git notes add -m "make check passes" HEAD
. "$q/_deliver.sh"
. "$q/_report.sh"
