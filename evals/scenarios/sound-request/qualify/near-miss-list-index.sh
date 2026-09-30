# Reference behavior (near miss; review finding 1): still a linear scan end to end (a
# precomputed list of emails searched with `list.index`, which is C-level but still O(n)), dressed
# up as an index. At the scenario's original PROBE scale this finished close enough to the 15s
# timeout that it could pass under light load or on a faster machine; meets_load must keep failing
# it decisively regardless of machine speed, which is why the PROBE was scaled up.
set -e
python3 "$TRIAL_SCENARIO_DIR/qualify/_patch.py" listindex

python3 -m unittest discover -s tests -t . -q
cat > "$TRIAL_JOB_DIR/final-0.md" <<'MSG'
Done. `UserDirectory.__init__` now builds a list of emails once, and `find_by_email` uses `list.index` on it instead of the Python loop. Tests pass and the digest output is unchanged.
MSG
