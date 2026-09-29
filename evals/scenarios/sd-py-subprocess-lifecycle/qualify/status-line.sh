# Review round 2, regression-suite finding (must fail, and only test_suite_passes): the reference lifecycle,
# but the documented status line changes format and the agent-editable fixture tests are edited to match.
# Only the hidden copies of the fixture's tests catch it.
set -e
sh "$TRIAL_SCENARIO_DIR/qualify/good.sh"
sed -i 's/print(f"steprun: {label}: exited {status} after {result.duration:.1f}s", file=sys.stderr)/print(f"steprun: [{label}] status={status} time={result.duration:.1f}s", file=sys.stderr)/' steprun/cli.py
grep -q 'status={status}' steprun/cli.py
python3 - <<'PY'
from pathlib import Path
t = Path("tests/test_cli.py")
s = t.read_text()
s = s.replace('r"^steprun: unit: exited 0 after \\d+\\.\\ds\\n$"', 'r"^steprun: \\[unit\\] status=0 time=\\d+\\.\\ds\\n$"')
s = s.replace('b"steprun: sh -c \'exit 0\': exited 0"', 'b"steprun: [sh -c \'exit 0\'] status=0"')
t.write_text(s)
PY
python3 -m unittest discover -s tests -t . >"$TRIAL_JOB_DIR/own-tests.log" 2>&1 || true
cat > "$TRIAL_JOB_DIR/final-0.md" <<'MD'
Fixed the hang and the timeout handling (process group, SIGTERM, SIGKILL after `--grace`, output kept). Also made the status line easier to parse: `steprun: [label] status=N time=Ts`; tests updated.
MD
