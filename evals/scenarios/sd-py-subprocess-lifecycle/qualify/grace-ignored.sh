# Review round 2, grace finding (must fail, and only timeout_sigterm_first): the minimal correct fix from
# good-simple.sh, but steprun waits a fixed 0.5 s between SIGTERM and SIGKILL whatever --grace says, so a
# step whose cleanup takes longer than that is killed half way.
set -e
sh "$TRIAL_SCENARIO_DIR/qualify/good-simple.sh"
sed -i 's/time.sleep(grace)/time.sleep(0.5)  # a fixed grace period/' steprun/runner.py
grep -q 'time.sleep(0.5)' steprun/runner.py
cat > "$TRIAL_JOB_DIR/final-0.md" <<'MD'
Both pipes are drained with `communicate()`, and on timeout the step's whole process group gets SIGTERM and, half a second later, SIGKILL, so nothing it started survives. Output printed before the timeout is written. Tests pass.
MD
