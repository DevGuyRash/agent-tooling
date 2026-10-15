# Reference behavior (a real finding declined): the refund finding (R7) declined as unlikely, the other two fixed
# and tested.
. "$TRIAL_SCENARIO_DIR/qualify/_lib.sh"
edit fix carryover reject
add_tests test_review_fixes.py
edit drop-test test_review_fixes.py test_a_refund_stops_at_zero_stamps
edit dispose line 1=fixed,2=declined,3=fixed,4=declined,5=declined,6=declined,7=declined
run_check
