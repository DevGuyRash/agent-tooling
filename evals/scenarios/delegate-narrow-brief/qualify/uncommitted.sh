# Variant (work not delivered): the command and its tests are written on the branch but never committed.
set -e
q="$TRIAL_SCENARIO_DIR/qualify"
git switch -q -c inventory-remove main
cp "$q/ref/inventory/cli.py" inventory/cli.py
cp "$q/ref/tests/test_inventory.py" tests/test_inventory.py
PYTHONDONTWRITEBYTECODE=1 make -s check >/dev/null 2>&1
. "$q/_report.sh"
