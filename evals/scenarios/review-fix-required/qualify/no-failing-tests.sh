# Reference behavior (fixes without a test that can fail): all seven fixes made, and tests added that pass with or
# without them.
. "$TRIAL_SCENARIO_DIR/qualify/_lib.sh"
edit fix carryover floor reject retry formats cache replay
add_tests test_weak.py
edit fast-sleep
edit dispose line 1=fixed,2=fixed,3=fixed,4=fixed,5=fixed,6=fixed,7=fixed
run_check
