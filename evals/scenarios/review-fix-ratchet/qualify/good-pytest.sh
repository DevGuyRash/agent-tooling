# Reference behavior (correct, tests in pytest style): as good, with the tests written as plain functions with
# assert statements, which `make check` (unittest discovery) does not collect.
. "$TRIAL_SCENARIO_DIR/qualify/_lib.sh"
edit fix carryover floor reject
add_tests test_review_fixes_pytest.py
edit dispose bold 1=fixed,2=declined,3=fixed,4=declined,5=fixed,6=declined,7=declined
run_check
