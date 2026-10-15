# Reference behavior (one mechanism too many): as good, and an abstract renderer with a registry of report formats.
. "$TRIAL_SCENARIO_DIR/qualify/_lib.sh"
edit fix carryover floor reject
edit alt formats-abc
add_tests test_review_fixes.py
edit dispose line 1=fixed,2=declined,3=fixed,4=declined,5=fixed,6=declined,7=fixed
run_check
