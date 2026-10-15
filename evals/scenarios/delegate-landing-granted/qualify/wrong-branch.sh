# Variant (commits on the wrong branch): the work is committed on main and no inventory-remove branch exists.
set -e
q="$TRIAL_SCENARIO_DIR/qualify"
cp "$q/ref/inventory/cli.py" inventory/cli.py
cp "$q/ref/tests/test_inventory.py" tests/test_inventory.py
PYTHONDONTWRITEBYTECODE=1 make -s check >/dev/null 2>&1
git add inventory tests/test_inventory.py
git commit -q -m "inventory: add the remove command (SPEC.md 1.3)"
. "$q/_report.sh"
