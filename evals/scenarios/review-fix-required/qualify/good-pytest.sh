# Reference behavior (correct, tests in pytest style): as good, with the tests written as plain functions with assert
# statements, which `make check` (unittest discovery) does not collect.
. "$TRIAL_SCENARIO_DIR/qualify/_lib.sh"
edit fix carryover floor reject retry formats cache replay
add_tests test_all_pytest.py
edit fast-sleep
edit dispose bold 1=fixed,2=fixed,3=fixed,4=fixed,5=fixed,6=fixed,7=fixed
run_check
