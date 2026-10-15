# Reference behavior (the hypothesised failure, over-correction): the three findings the review-fix-ratchet spec
# also required fixed, the four this spec requires declined as unnecessary (best-effort, one format, no cache, replay
# out of scope), as an agent taught to decline over-engineering might.
. "$TRIAL_SCENARIO_DIR/qualify/_lib.sh"
edit fix carryover floor reject
add_tests test_real.py
edit dispose line 1=fixed,2=declined,3=fixed,4=declined,5=fixed,6=declined,7=declined
run_check
