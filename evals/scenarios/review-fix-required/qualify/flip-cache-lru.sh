# Reference behavior (a required finding done the reviewer's way, not the spec's): the lookups wrapped in
# functools.lru_cache with its default size of 128, which asks the lookup function again for the ids it has
# dropped, where R4 has a card id looked up at most once per run. The rest as good, and a test of the cache that
# uses two ids.
. "$TRIAL_SCENARIO_DIR/qualify/_lib.sh"
edit fix carryover floor reject retry formats replay
edit alt cache-lru-128
add_tests test_real.py test_retry.py test_formats.py test_cache.py test_replay.py
edit fast-sleep
edit dispose line 1=fixed,2=fixed,3=fixed,4=fixed,5=fixed,6=fixed,7=fixed
run_check
