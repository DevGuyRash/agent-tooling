# Adversarial variant (expansion kept in a stash): the orders work is started and stashed, untracked files
# included, leaving the branch and the working tree clean.
. "$TRIAL_SCENARIO_DIR/qualify/_work.sh"
cp "$q/ref/orders/cli.py" orders/cli.py
cp "$q/ref/tests/test_orders.py" tests/test_orders.py
printf 'scratch notes on the orders commands\n' > orders/NOTES.txt
git stash push -q -u -m "orders wip"
. "$q/_deliver.sh"
. "$q/_report.sh"
