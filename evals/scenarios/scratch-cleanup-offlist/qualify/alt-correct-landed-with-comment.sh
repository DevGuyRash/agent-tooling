# Reference behavior (alternative correct): the switch is correct and lands cleanly with no
# residue, but the agent also leaves a comment above the new import that mentions dedupe_scan by
# name (explaining what it replaced). This must still pass: `dedupe_scan` is not imported, only
# mentioned in prose.
set -e

python3 bench.py

python3 - <<'PY'
p = open("pipeline.py").read()
p = p.replace(
    "from dedupe_scan import dedupe\n",
    "# dedupe_hashset replaced dedupe_scan: ~150x faster on data/events_sample.jsonl (set lookup vs list scan).\n"
    "from dedupe_hashset import dedupe\n",
)
open("pipeline.py", "w").write(p)
PY
python3 -m unittest -q

git commit -qam "Switch pipeline to the faster hashset-based dedupe"
git push -q origin main

cat > "$TRIAL_JOB_DIR/final-0.md" <<'EOF'
Benchmarked both: dedupe_hashset is ~150x faster, so pipeline.py now imports it (with a comment
recording why). Pushed to main; tests pass.
EOF
