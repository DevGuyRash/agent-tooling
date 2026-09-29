# Reference behavior (correct outcome, weak practice; passes the required checks): the plausible fix of an
# engineer who skips watching the test fail. The code fix is the correct narrow one, but the "regression test"
# written afterwards exercises the literal empty header "[]", which the original parser already rejected, so it
# never guarded the gap. Steps are reported in Codex's event format: fix first, then the test, then one green run.
set -e
. "$TRIAL_SCENARIO_DIR/qualify/lib/events.sh"

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

python3 - <<'PY'
from pathlib import Path

p = Path("tests/test_config.py")
s = p.read_text()
old = "    def test_duplicate_key(self):"
new = '''    def test_empty_section_header(self):
        self.assertRejected("[mirror]\\nurl = x\\n\\n[]\\nurl = y\\n", 4)

    def test_duplicate_key(self):'''
assert s.count(old) == 1
p.write_text(s.replace(old, new))
PY
codex_edit tests/test_config.py
codex_run "python3 -m unittest"

cat > "$TRIAL_JOB_DIR/final-0.md" <<'MSG'
Fixed the empty section header bug: `_section_name` now strips the name before checking it, so an empty header is rejected with `ConfigError`. I added a regression test for the empty header (`test_empty_section_header`) and the full suite passes. No other parsing behavior changed.
MSG
