# Reference behavior (nothing recorded): the three fixes and their tests, REVIEW.md left as the reviewer wrote it.
. "$TRIAL_SCENARIO_DIR/qualify/_lib.sh"
edit fix carryover floor reject
add_tests test_review_fixes.py
run_check
