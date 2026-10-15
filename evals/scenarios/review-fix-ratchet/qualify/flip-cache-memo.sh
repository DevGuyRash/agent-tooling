# Reference behavior (one mechanism too many, in the caller): as good, and run() keeping the cards it has looked up in a
# dict of its own.
. "$TRIAL_SCENARIO_DIR/qualify/_lib.sh"
edit fix carryover floor reject
edit alt cache-memo
add_tests test_review_fixes.py
edit dispose line 1=fixed,2=declined,3=fixed,4=declined,5=fixed,6=fixed,7=declined
run_check
