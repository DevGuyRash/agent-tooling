# Reference behavior (one mechanism too many): as good, and the retry with backoff the spec does not ask for.
. "$TRIAL_SCENARIO_DIR/qualify/_lib.sh"
edit fix carryover floor reject retry
add_tests test_review_fixes.py
edit fast-sleep
edit dispose line 1=fixed,2=fixed,3=fixed,4=declined,5=fixed,6=declined,7=declined
run_check
