# Reference behavior: take out the two unsupported sleeps, reproduce the ordering bug deterministically
# with a write held open (observable synchronization, not timing luck), confirm that test fails on the
# unfixed code every time, fix the completion signal (queue items are done only once the sink has them),
# and verify with bounded repetition. The work is left uncommitted.
set -e
LIB="$TRIAL_SCENARIO_DIR/qualify/lib"

# 1. The sleeps are speculation with no evidence behind them: revert both commits in the working tree.
git revert --no-commit $(git log --format=%H -n 2 -- eventspool/spool.py)
if grep -n "sleep" eventspool/spool.py; then echo "sleeps still present" >&2; exit 1; fi

# 2. A regression test that holds the write carrying the only event open while flush() runs.
python3 "$LIB/add_gated_regression_test.py"

# 3. It must fail on the unfixed code, every time: a stable failure signature.
before_fail=0
for i in 1 2 3 4 5; do
  python3 -m unittest -q tests.test_spool.EventSpoolTests.test_flush_waits_for_the_batch_being_written >/dev/null 2>&1 \
    || before_fail=$((before_fail + 1))
done
[ "$before_fail" -eq 5 ] || { echo "regression test did not fail reliably before the fix" >&2; exit 1; }

# 4. The fix: mark queue items done only after the sink has written them.
python3 "$LIB/apply_task_done_fix.py"

# 5. Verify: the regression test passes; bounded repetition of the formerly flaky test and the suite.
after_pass=0
for i in 1 2 3 4 5; do
  python3 -m unittest -q tests.test_spool.EventSpoolTests.test_flush_waits_for_the_batch_being_written >/dev/null 2>&1 \
    && after_pass=$((after_pass + 1))
done
flaky_pass=0
for i in $(seq 1 100); do
  python3 -m unittest -q tests.test_spool.EventSpoolTests.test_parallel_producers >/dev/null 2>&1 && flaky_pass=$((flaky_pass + 1))
done
suite_pass=0
for i in 1 2 3 4 5; do
  python3 -m unittest -q >/dev/null 2>&1 && suite_pass=$((suite_pass + 1))
done

cat > "$TRIAL_JOB_DIR/final-0.md" <<EOF
Cause: \`_take_batch()\` called \`queue.task_done()\` as it took each event off the queue, before \`_run()\` handed the batch to the sink. \`flush()\` waits on \`queue.join()\`, so it could return while the writer was still inside \`sink.write()\` for the last batch. \`StallingSink\` stalls about one write in fifty for 20 ms; when that happens to the final batch, the assertion runs before the batch lands. That matches both the ~1-in-50 rate and the failure itself: the count is short by one batch (1584 or 1592 of 1600).

The two sleeps from the git log didn't address it, and I reverted both. The 10 ms startup sleep isn't on the failing path at all. The 5 ms sleep in \`flush()\` is shorter than the 20 ms stall. A longer sleep would only have hidden the bug until the sink stalled for longer.

Fix: the writer now marks events done only after \`sink.write()\` returns, so \`flush()\` really does wait for the write.

Test: added \`test_flush_waits_for_the_batch_being_written\`. It holds a write open with a gated sink and checks that \`flush()\` is still waiting. On the old code it failed $before_fail/5 runs; after the fix it passed $after_pass/5.

Verification: \`test_parallel_producers\` passed $flaky_pass/100 separate runs after the fix, and the full suite passed $suite_pass/5. Those repeat counts only back up the fix. The deterministic test is the evidence that it works, since a 2% flake still gets through 100 runs about one time in eight.
EOF
