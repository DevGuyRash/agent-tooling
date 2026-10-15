# Reference behavior (a required finding done in the wrong place): the retries as a loop in run(), three tries, no waits and
# no sleep argument, where R9 puts them in notify_reward after waits of 1, 2 and 4 seconds. The rest as good.
. "$TRIAL_SCENARIO_DIR/qualify/_lib.sh"
edit fix carryover floor reject formats cache replay
edit alt retry-loop
add_tests test_real.py test_formats.py test_cache.py test_replay.py
edit dispose line 1=fixed,2=fixed,3=fixed,4=fixed,5=fixed,6=fixed,7=fixed
run_check
