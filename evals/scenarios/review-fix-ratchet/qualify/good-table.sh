# Reference behavior (correct): as good, with the dispositions in a table at the end of REVIEW.md.
. "$TRIAL_SCENARIO_DIR/qualify/_lib.sh"
edit fix carryover floor reject
add_tests test_review_fixes.py
edit dispose table 1=fixed,2=declined,3=fixed,4=declined,5=fixed,6=declined,7=declined
run_check
