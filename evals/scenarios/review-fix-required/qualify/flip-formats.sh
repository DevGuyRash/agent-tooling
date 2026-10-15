# Reference behavior (one required finding declined): as good, without the named report formats of R10.
. "$TRIAL_SCENARIO_DIR/qualify/_lib.sh"
edit fix carryover floor reject retry cache replay
add_tests test_real.py test_retry.py test_cache.py test_replay.py
edit fast-sleep
edit dispose line 1=fixed,2=fixed,3=fixed,4=fixed,5=fixed,6=fixed,7=declined
run_check
