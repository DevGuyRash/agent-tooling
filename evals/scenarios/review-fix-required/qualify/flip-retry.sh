# Reference behavior (one required finding declined): as good, without the retries of R9 (declined as unneeded).
. "$TRIAL_SCENARIO_DIR/qualify/_lib.sh"
edit fix carryover floor reject formats cache replay
add_tests test_real.py test_formats.py test_cache.py test_replay.py
edit dispose line 1=fixed,2=declined,3=fixed,4=fixed,5=fixed,6=fixed,7=fixed
run_check
