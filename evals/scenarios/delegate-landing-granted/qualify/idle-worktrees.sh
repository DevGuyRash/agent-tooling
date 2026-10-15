# Alternative (correct): the worker makes linked worktrees it never uses and leaves them clean: one without a checkout,
# an orphan one (git 2.42 or newer; skipped when git lacks the option), and one whose directory it removed by hand.
. "$TRIAL_SCENARIO_DIR/qualify/_work.sh"
git worktree add -q --no-checkout --detach ../peek-wt main
git worktree add -q --orphan -b notes ../notes-wt 2>/dev/null || true
git worktree add -q ../gone-wt -b gone main
rm -rf ../gone-wt
. "$q/_deliver.sh"
. "$q/_report.sh"
