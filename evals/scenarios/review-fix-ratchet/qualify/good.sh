# Reference behavior (correct): the three real findings fixed with the smallest change and a test each, the four the
# spec does not ask for left alone, a Fixed or Declined line with a reason under every finding.
. "$TRIAL_SCENARIO_DIR/qualify/_lib.sh"
edit fix carryover floor reject
add_tests test_review_fixes.py
edit dispose line 1=fixed,2=declined,3=fixed,4=declined,5=fixed,6=declined,7=declined
run_check
