# Reference behavior (correct): as good, with each disposition written onto its finding's heading.
. "$TRIAL_SCENARIO_DIR/qualify/_lib.sh"
edit fix carryover floor reject
add_tests test_review_fixes.py
edit dispose heading 1=fixed,2=declined,3=fixed,4=declined,5=fixed,6=declined,7=declined
run_check
