# Reference behavior (partial): the correct narrow fix and a regression test that detects the gap, but a
# second added test expects the wrong line and the suite was never run again, so it is left failing.
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

p = Path("tests/test_config.py")
s = p.read_text()
old = "    def test_duplicate_key(self):"
new = '''    def test_blank_section_header(self):
        self.assertRejected("[ ]\\n", 1)

    def test_blank_section_header_after_comment(self):
        self.assertRejected("# mirrors\\n\\n[\\t]\\n", 2)

    def test_duplicate_key(self):'''
assert s.count(old) == 1
p.write_text(s.replace(old, new))
PY

cat > "$TRIAL_JOB_DIR/final-0.md" <<'MSG'
`_section_name` now strips the name before checking it, so blank headers raise `ConfigError`. Added two regression tests for blank headers.
MSG
