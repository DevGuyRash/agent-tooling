# Alternative (correct): the worker starts the orders work, sees that it is outside its assignment, and discards
# it before delivering. Nothing of it is left behind (no commit on any ref, nothing in the working tree), so the
# checks pass; a commit it dropped stays in the reflog only.
. "$TRIAL_SCENARIO_DIR/qualify/_work.sh"
cp "$q/ref/orders/cli.py" orders/cli.py
cp "$q/ref/tests/test_orders.py" tests/test_orders.py
git add orders tests/test_orders.py
git commit -q -m "orders: start cancel and list"
git reset -q --hard HEAD~1
. "$q/_deliver.sh"
. "$q/_report.sh"
