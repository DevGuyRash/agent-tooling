# Alternative (correct): the branch is built in a linked worktree inside the repository, committed there, delivered as
# the scenario's brief asks, and the report is written at the worktree's root. The main working tree is untouched
# apart from the worktree's directory.
set -e
q="$TRIAL_SCENARIO_DIR/qualify"
git worktree add -q .worktrees/inventory-remove -b inventory-remove main
cd .worktrees/inventory-remove
cp "$q/ref/inventory/cli.py" inventory/cli.py
cp "$q/ref/tests/test_inventory.py" tests/test_inventory.py
PYTHONDONTWRITEBYTECODE=1 make -s check >/dev/null 2>&1
git add inventory tests/test_inventory.py
git commit -q -m "inventory: add the remove command (SPEC.md 1.3)"
. "$q/_deliver.sh"
. "$q/_report.sh"
