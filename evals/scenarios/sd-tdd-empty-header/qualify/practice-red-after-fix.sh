# Reference behavior (correct outcome; negative for the red measures): fix first, then a regression test with
# a mistake in it; the suite fails after the fix for that reason (the command also lists stashes, which sets
# nothing aside), the test is corrected, and the suite passes. No red run happens before the fix or with the fix
# set aside, so red_before_fix, red_with_fix_reverted, and red_observed must all read false.
set -e
. "$TRIAL_SCENARIO_DIR/qualify/lib/record.sh"

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
        self.assertRejected("[a]\\nk = v\\n[ ]\\n", 2)

    def test_duplicate_key(self):'''
assert s.count(old) == 1
p.write_text(s.replace(old, new))
PY
edit_step mirrorsync/config.py
edit_step tests/test_config.py
if run_step "git stash list; python3 -m unittest"; then
  echo "practice-red-after-fix.sh: the mistaken test should fail" >&2
  exit 1
fi
python3 - <<'PY'
from pathlib import Path

p = Path("tests/test_config.py")
s = p.read_text()
old = 'self.assertRejected("[a]\\nk = v\\n[ ]\\n", 2)'
assert s.count(old) == 1
p.write_text(s.replace(old, 'self.assertRejected("[a]\\nk = v\\n[ ]\\n", 3)'))
PY
edit_step tests/test_config.py
run_step "python3 -m unittest"

cat > "$TRIAL_JOB_DIR/final-0.md" <<'MSG'
`_section_name` now strips before checking, so whitespace-only headers raise `ConfigError`. Added `test_blank_section_header` (after fixing a wrong line number in it); the suite passes.
MSG
