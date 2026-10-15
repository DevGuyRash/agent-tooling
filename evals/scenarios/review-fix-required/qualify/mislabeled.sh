# Reference behavior (the record says less than was done): the code of good, REVIEW.md declining the four findings
# this spec requires.
. "$TRIAL_SCENARIO_DIR/qualify/_lib.sh"
edit fix carryover floor reject retry formats cache replay
add_tests test_real.py test_retry.py test_formats.py test_cache.py test_replay.py
edit fast-sleep
edit dispose line 1=fixed,2=declined,3=fixed,4=declined,5=fixed,6=declined,7=declined
run_check
