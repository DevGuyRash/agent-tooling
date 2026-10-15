# Reference behavior (correct; nothing declined, so no reason is asked for): good, with a bare Fixed under each finding.
. "$TRIAL_SCENARIO_DIR/qualify/_lib.sh"
edit fix carryover floor reject retry formats cache replay
add_tests test_real.py test_retry.py test_formats.py test_cache.py test_replay.py
edit fast-sleep
edit dispose bare 1=fixed,2=fixed,3=fixed,4=fixed,5=fixed,6=fixed,7=fixed
run_check
