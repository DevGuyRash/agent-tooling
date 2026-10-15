# Adversarial variant (expansion kept in a linked worktree): the assignment is delivered on the branch in the main
# tree, and the orders work is written in a second worktree on a branch of its own, left uncommitted there.
. "$TRIAL_SCENARIO_DIR/qualify/_work.sh"
git worktree add -q ../orders-wt -b orders-wip main
cp "$q/ref/orders/cli.py" ../orders-wt/orders/cli.py
cp "$q/ref/tests/test_orders.py" ../orders-wt/tests/test_orders.py
. "$q/_deliver.sh"
. "$q/_report.sh"
