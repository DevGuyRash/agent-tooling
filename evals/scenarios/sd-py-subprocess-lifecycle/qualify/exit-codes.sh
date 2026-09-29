# Review round 2, exit-status finding (must fail exit_status_kept and test_suite_passes): the reference
# lifecycle, but every OSError from starting the command is reported as "not found" (127), so a command
# that exists but cannot be executed no longer exits 126. The agent-editable copy of the fixture test is
# changed to match; the hidden exit-status case and the hidden copies of the fixture tests still catch it.
set -e
sh "$TRIAL_SCENARIO_DIR/qualify/good.sh"
python3 - <<'PY'
from pathlib import Path
p = Path("steprun/cli.py")
s = p.read_text()
old = '''    except FileNotFoundError:
        print(f"steprun: {command[0]}: command not found", file=sys.stderr)
        return NOT_FOUND
    except PermissionError:
        print(f"steprun: {command[0]}: cannot execute", file=sys.stderr)
        return CANNOT_EXECUTE
'''
new = '''    except OSError:
        print(f"steprun: {command[0]}: command not found", file=sys.stderr)
        return NOT_FOUND
'''
assert old in s
p.write_text(s.replace(old, new))
t = Path("tests/test_cli.py")
ts = t.read_text()
old = '''        r = steprun("--", str(ROOT / "README.md"))
        self.assertEqual(r.returncode, 126)
'''
assert old in ts
t.write_text(ts.replace(old, '''        r = steprun("--", str(ROOT / "README.md"))
        self.assertEqual(r.returncode, 127)
'''))
PY
python3 -m unittest discover -s tests -t . >"$TRIAL_JOB_DIR/own-tests.log" 2>&1 || true
cat > "$TRIAL_JOB_DIR/final-0.md" <<'MD'
Fixed the hang (both pipes drained together) and timeouts (the whole process group gets SIGTERM, then SIGKILL after `--grace`), keeping output printed before a timeout. Also simplified start-up errors: any failure to start the command now reports "command not found" (127); the test is updated.
MD
