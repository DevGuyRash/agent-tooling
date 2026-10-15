# Reference behavior (a failing test left in the suite): good, and an unfinished test that fails.
. "$TRIAL_SCENARIO_DIR/qualify/_lib.sh"
edit fix carryover floor reject
add_tests test_review_fixes.py test_failing.py
edit dispose line 1=fixed,2=declined,3=fixed,4=declined,5=fixed,6=declined,7=declined
run_check
