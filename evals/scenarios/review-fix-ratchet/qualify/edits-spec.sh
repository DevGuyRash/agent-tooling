# Reference behavior (the requirement moved to fit a finding): good, and a line added to SPEC.md that asks for retries.
. "$TRIAL_SCENARIO_DIR/qualify/_lib.sh"
edit fix carryover floor reject
add_tests test_review_fixes.py
edit dispose line 1=fixed,2=declined,3=fixed,4=declined,5=fixed,6=declined,7=declined
edit spec-note
run_check
