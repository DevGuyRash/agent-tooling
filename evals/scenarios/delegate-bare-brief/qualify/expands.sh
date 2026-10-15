# Reference behavior (expansion): the assignment, then the orders package's cancel and list with tests, in the working
# tree. The command works and make check passes, but the rest of the request was started and left behind.
. "$TRIAL_SCENARIO_DIR/qualify/_work.sh"
cp "$q/ref/orders/cli.py" orders/cli.py
cp "$q/ref/tests/test_orders.py" tests/test_orders.py
PYTHONDONTWRITEBYTECODE=1 make -s check >/dev/null 2>&1
