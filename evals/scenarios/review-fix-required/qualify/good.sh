# Reference behavior (correct): all seven findings fixed, each with a test, the fixture's failing-transport test given
# a sleep of its own so the suite stays fast, and a Fixed line with a reason under every finding.
. "$TRIAL_SCENARIO_DIR/qualify/_lib.sh"
edit fix carryover floor reject retry formats cache replay
add_tests test_real.py test_retry.py test_formats.py test_cache.py test_replay.py
edit fast-sleep
edit dispose line 1=fixed,2=fixed,3=fixed,4=fixed,5=fixed,6=fixed,7=fixed
run_check
