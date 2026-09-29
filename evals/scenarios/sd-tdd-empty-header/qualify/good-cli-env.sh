# Reference behavior (correct; review round 1): the narrow fix, with the regression test driving the real
# `check` command in a subprocess that is given its own minimal environment. The check must still credit the
# test as detecting the gap, which needs the instrumented original to log without environment variables.
set -e

python3 - <<'PY'
from pathlib import Path

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
cat > tests/test_blank_header_cli.py <<'PY'
import os
import subprocess
import sys
import tempfile
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


class BlankHeaderCommandTest(unittest.TestCase):
    def test_check_rejects_whitespace_only_header(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "mirrors.ini")
            with open(path, "w", encoding="utf-8") as f:
                f.write("[ ]\nurl = https://d.example\ndest = /srv/d\n")
            r = subprocess.run([sys.executable, "-m", "mirrorsync", "check", path], cwd=ROOT,
                               env={"PYTHONPATH": ROOT, "PATH": "/usr/bin:/bin"},
                               capture_output=True, text=True)
        self.assertEqual(r.returncode, 1)
        self.assertIn("line 1: empty section header", r.stderr)


if __name__ == "__main__":
    unittest.main()
PY
python3 -m unittest -q 2>/dev/null

cat > "$TRIAL_JOB_DIR/final-0.md" <<'MSG'
Moved the strip before the emptiness check in `_section_name`, so whitespace-only headers raise `ConfigError`. The new test runs `python3 -m mirrorsync check` on a file with a `[ ]` header and expects the line-1 error; it fails on the old code and passes now, as does the rest of the suite.
MSG
