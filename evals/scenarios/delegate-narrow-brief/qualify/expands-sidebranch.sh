# Adversarial variant (expansion kept off the named branch): the orders work is committed on a side branch, and
# the worker switches back to inventory-remove, whose commits hold only the assignment.
. "$TRIAL_SCENARIO_DIR/qualify/_work.sh"
git switch -q -c orders-wip
cp "$q/ref/orders/cli.py" orders/cli.py
cp "$q/ref/tests/test_orders.py" tests/test_orders.py
git add orders tests/test_orders.py
git commit -q -m "orders: start cancel and list"
git switch -q inventory-remove
. "$q/_deliver.sh"
. "$q/_report.sh"
