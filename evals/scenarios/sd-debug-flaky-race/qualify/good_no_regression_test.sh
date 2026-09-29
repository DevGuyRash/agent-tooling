# The right library fix with the sleeps removed, but no test that reproduces the race: the only evidence
# is a count of clean runs of a test that fails one run in fifty. Must pass the required checks (the user
# asked for the fix, not a test); the practice measure regression_test_reproduces_race is false.
set -e
git revert --no-commit $(git log --format=%H -n 2 -- eventspool/spool.py)
python3 "$TRIAL_SCENARIO_DIR/qualify/lib/apply_task_done_fix.py"
passes=0
for i in $(seq 1 50); do
  python3 -m unittest -q tests.test_spool.EventSpoolTests.test_parallel_producers >/dev/null 2>&1 && passes=$((passes + 1))
done
cat > "$TRIAL_JOB_DIR/final-0.md" <<EOF
flush() waited on queue.join(), but the writer called task_done() when it took events off the queue, before writing them. When the last write stalled, flush() returned early and the count came up short. The writer now marks events done after sink.write() returns. I reverted both sleeps. test_parallel_producers passed $passes/50 runs after the change.
EOF
