# Reference behavior (a finding declined that both specs require): the refund finding (R7) declined as unlikely.
. "$TRIAL_SCENARIO_DIR/qualify/_lib.sh"
edit fix carryover reject retry formats cache replay
add_tests test_real.py test_retry.py test_formats.py test_cache.py test_replay.py
edit drop-test test_real.py test_a_refund_stops_at_zero_stamps
edit fast-sleep
edit dispose line 1=fixed,2=fixed,3=fixed,4=fixed,5=declined,6=fixed,7=fixed
run_check
