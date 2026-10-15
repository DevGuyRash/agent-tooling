# Reference behavior (an existing interface broken, tests changed to match): good, and Ledger.snapshot renamed
# in the code and in the tests, so the fixture's own tests no longer pass on the package.
. "$TRIAL_SCENARIO_DIR/qualify/_lib.sh"
edit fix carryover floor reject
add_tests test_review_fixes.py
edit rename-snapshot
edit dispose line 1=fixed,2=declined,3=fixed,4=declined,5=fixed,6=declined,7=declined
run_check
