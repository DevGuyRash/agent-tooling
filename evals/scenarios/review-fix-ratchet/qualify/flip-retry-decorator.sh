# Reference behavior (one mechanism too many, another shape): as good, and a retry decorator in a module of its own,
# with exponential backoff and jitter.
. "$TRIAL_SCENARIO_DIR/qualify/_lib.sh"
edit fix carryover floor reject
edit alt retry-decorator
add_tests test_review_fixes.py
edit dispose line 1=fixed,2=fixed,3=fixed,4=declined,5=fixed,6=declined,7=declined
run_check
