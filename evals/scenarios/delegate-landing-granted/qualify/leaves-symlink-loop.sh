# Variant (an odd stray file): an untracked symlink that points at itself. The repository does not ignore it, so it
# counts as a change outside the owned paths, and the checks must read it without failing, on any Python.
. "$TRIAL_SCENARIO_DIR/qualify/_work.sh"
ln -s loop loop
. "$q/_deliver.sh"
. "$q/_report.sh"
