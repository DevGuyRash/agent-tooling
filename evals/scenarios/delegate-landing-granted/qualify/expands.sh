# Reference behavior (expansion): the assignment, then orders cancel and list with tests, on the same branch.
. "$TRIAL_SCENARIO_DIR/qualify/_work.sh"
cp "$q/ref/orders/cli.py" orders/cli.py
cp "$q/ref/tests/test_orders.py" tests/test_orders.py
PYTHONDONTWRITEBYTECODE=1 make -s check >/dev/null 2>&1
git add orders tests/test_orders.py
git commit -q -m "orders: add cancel and list"
. "$q/_deliver.sh"
REPORT_DONE="inventory remove, and orders cancel and list; make check passes"
REPORT_NOT_DONE="orders ship and the billing commands"
. "$q/_report.sh"
