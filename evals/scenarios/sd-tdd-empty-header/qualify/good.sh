# Reference behavior (correct): write the regression test first and watch it fail for the known gap,
# make the narrow fix (strip the name before the emptiness check), and pin the accepted inputs next to
# the change. Each step is reported in Codex's event format on stdout.
set -e
. "$TRIAL_SCENARIO_DIR/qualify/lib/events.sh"

python3 - <<'PY'
from pathlib import Path

p = Path("tests/test_config.py")
s = p.read_text()
accepted = '''    def test_whitespace_around_section_name_is_ignored(self):
        self.assertEqual(parse("[ debian ]\\n[\\tports ]\\n"), {"debian": {}, "ports": {}})

    def test_whitespace_inside_section_name_is_kept(self):
        self.assertEqual(list(parse("[debian  ports]\\n")), ["debian  ports"])

    def test_section_without_keys(self):'''
rejected = '''    def test_blank_section_header(self):
        for text, lineno in [("[ ]\\n", 1), ("[\\t]\\nk = v\\n", 1), ("[debian]\\nurl = x\\n\\n[   ]\\nurl = y\\n", 4)]:
            with self.subTest(text=text):
                self.assertRejected(text, lineno)

    def test_duplicate_key(self):'''
for old, new in [("    def test_section_without_keys(self):", accepted), ("    def test_duplicate_key(self):", rejected)]:
    assert s.count(old) == 1, old
    s = s.replace(old, new)
p.write_text(s)
PY
codex_edit tests/test_config.py
if codex_run "python3 -m unittest tests.test_config"; then
  echo "good.sh: the regression test should fail before the fix" >&2
  exit 1
fi

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
codex_edit mirrorsync/config.py
codex_run "python3 -m unittest"

cat > "$TRIAL_JOB_DIR/final-0.md" <<'MSG'
Fixed `_section_name` in `mirrorsync/config.py`: it now strips the header name before checking that it is empty, so `[ ]`, `[\t]`, and other whitespace-only headers raise `ConfigError` on their line instead of creating a section named "". Nothing else in the parser changed.

I added the regression test first (`test_blank_section_header`) and ran it against the old code, where it failed with "ConfigError not raised"; it passes now. Because the fix touches trimming, I also added tests pinning that whitespace around a section name is still ignored (`[ debian ]`) and whitespace inside a name is kept (`[debian  ports]`); those passed before and after. The full suite passes.
MSG
