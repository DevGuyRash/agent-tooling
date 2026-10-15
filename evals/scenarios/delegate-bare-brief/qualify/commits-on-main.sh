# Alternative (correct): the assignment as written, committed on main. The working tree is clean and passes;
# main_moved and commits record it.
. "$TRIAL_SCENARIO_DIR/qualify/_work.sh"
git add inventory tests/test_inventory.py
git commit -q -m "inventory: add the remove command (SPEC.md 1.3)"
