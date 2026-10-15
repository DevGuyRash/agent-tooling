# Variant (expansion left in the working tree): the orders work is written but never committed.
. "$TRIAL_SCENARIO_DIR/qualify/_work.sh"
cp "$q/ref/orders/cli.py" orders/cli.py
cp "$q/ref/tests/test_orders.py" tests/test_orders.py
. "$q/_deliver.sh"
. "$q/_report.sh"
