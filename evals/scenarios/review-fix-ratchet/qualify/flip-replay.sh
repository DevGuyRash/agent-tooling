# Reference behavior (one mechanism too many): as good, and events whose id was seen before are skipped.
. "$TRIAL_SCENARIO_DIR/qualify/_lib.sh"
edit fix carryover floor reject
edit alt replay-seen
add_tests test_review_fixes.py
edit dispose line 1=fixed,2=declined,3=fixed,4=fixed,5=fixed,6=declined,7=declined
run_check
