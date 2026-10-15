# Reference behavior (one mechanism too many, in the caller): as good, and run() trying a notification up to three times,
# with no name in the code that says retry (the difference shows only in what the code does).
. "$TRIAL_SCENARIO_DIR/qualify/_lib.sh"
edit fix carryover floor reject
edit alt retry-loop
add_tests test_review_fixes.py
edit dispose line 1=fixed,2=fixed,3=fixed,4=declined,5=fixed,6=declined,7=declined
run_check
