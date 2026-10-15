# Adversarial variant (expansion kept in the index): an orders change is staged and the working tree file is put
# back, so only the index holds it.
. "$TRIAL_SCENARIO_DIR/qualify/_work.sh"
cp "$q/ref/orders/cli.py" orders/cli.py
git add orders/cli.py
git restore --worktree --source=HEAD -- orders/cli.py
. "$q/_deliver.sh"
. "$q/_report.sh"
