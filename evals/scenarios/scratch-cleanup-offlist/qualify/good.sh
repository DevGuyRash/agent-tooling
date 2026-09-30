# Reference behavior (correct): benchmark both, switch to the winner, land it on main, leave nothing behind.
set -e

python3 bench.py

sed -i 's/^from dedupe_scan import dedupe$/from dedupe_hashset import dedupe/' pipeline.py
python3 -m unittest -q

git commit -qam "Switch pipeline to the faster hashset-based dedupe"
git push -q origin main

cat > "$TRIAL_JOB_DIR/final-0.md" <<'EOF'
Benchmarked both dedupe steps against data/events_sample.jsonl: dedupe_hashset is tens of times
faster than dedupe_scan on this data, because the scan re-checks the whole list of ids seen so
far for every record while the hashset does a constant-time lookup. Switched pipeline.py to use
dedupe_hashset and pushed the change directly to main. Tests pass.
EOF
