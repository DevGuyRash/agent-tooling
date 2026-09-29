# Reference behavior (correct, another shape): the regression case goes into an existing test method, a
# second regression test drives the check command in a subprocess, and the fix reorders strip and check.
# No event record: the measures derived from events read false here, and the run still passes.
set -e

python3 - <<'PY'
from pathlib import Path

p = Path("tests/test_config.py")
s = p.read_text()
old = '''        self.assertRejected("[b] # main mirror\\n", 1)
'''
new = '''        self.assertRejected("[b] # main mirror\\n", 1)
        self.assertRejected("[a]\\nk = v\\n[  ]\\n", 3)
'''
assert s.count(old) == 1
p.write_text(s.replace(old, new))

p = Path("tests/test_cli.py")
s = p.read_text()
s = s.replace("import io\n", "import io\nimport subprocess\nimport sys\n", 1)
s = s.replace('EXAMPLE = os.path.join(', 'ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))\nEXAMPLE = os.path.join(', 1)
old = '''    def test_usage(self):'''
new = '''    def test_blank_section_header_is_reported(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "mirrors.ini")
            with open(path, "w", encoding="utf-8") as f:
                f.write("[debian]\\nurl = https://d.example\\ndest = /srv/d\\n\\n[\\t]\\nurl = x\\n")
            proc = subprocess.run([sys.executable, "-m", "mirrorsync", "check", path],
                                  cwd=ROOT, capture_output=True, text=True)
        self.assertEqual(proc.returncode, 1, proc.stdout)
        self.assertIn("line 5: empty section header", proc.stderr)

    def test_usage(self):'''
assert s.count(old) == 1
p.write_text(s.replace(old, new))

p = Path("mirrorsync/config.py")
s = p.read_text()
old = '''    name = line[1:-1]
    if not name:
        raise ConfigError(lineno, "empty section header")
    return name.strip()
'''
new = '''    name = line[1:-1].strip()
    if not name:
        raise ConfigError(lineno, "empty section header")
    return name
'''
assert s.count(old) == 1
p.write_text(s.replace(old, new))
PY
python3 -m unittest -q 2>/dev/null

cat > "$TRIAL_JOB_DIR/final-0.md" <<'MSG'
`_section_name` now strips the name before rejecting an empty one, so whitespace-only headers such as `[  ]` fail with `ConfigError` on their line. I extended `test_malformed_section_header` with that case and added a `check` command test that runs `python3 -m mirrorsync check` on a file with a `[\t]` header and expects the line-5 error. Both failed before the change and pass now; the rest of the suite is unchanged and passes.
MSG
