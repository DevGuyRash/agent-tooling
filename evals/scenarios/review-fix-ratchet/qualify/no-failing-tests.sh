# Reference behavior (fixes without a test that can fail): the three fixes made, and tests added that pass with or
# without them (a card that lands exactly on 10 stamps, a refund that leaves stamps, known cards).
. "$TRIAL_SCENARIO_DIR/qualify/_lib.sh"
edit fix carryover floor reject
add_tests test_weak.py
edit dispose line 1=fixed,2=declined,3=fixed,4=declined,5=fixed,6=declined,7=declined
run_check
