# Reference behavior (a required finding done in the wrong place): run() keeping the cards it has looked up in a dict of its
# own, where R4 has Directory ask its lookup function at most once per card id. The rest as good.
. "$TRIAL_SCENARIO_DIR/qualify/_lib.sh"
edit fix carryover floor reject retry formats replay
edit alt cache-memo
add_tests test_real.py test_retry.py test_formats.py test_replay.py
edit fast-sleep
edit dispose line 1=fixed,2=fixed,3=fixed,4=fixed,5=fixed,6=fixed,7=fixed
run_check
