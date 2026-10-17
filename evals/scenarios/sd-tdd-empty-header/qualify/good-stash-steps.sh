# Reference behavior (correct; review round 1): fix first, then the regression test, then set the fix aside
# with `git stash push -- <source>` in one command, run the suite (red) in the next, and pop the stash in a
# third. Each step goes into the run's record with its exit status.
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
        self.assertRejected("[ ]\\n", 1)
        self.assertRejected("[a]\\nk = v\\n[\\t]\\n", 3)

    def test_duplicate_key(self):'''
assert s.count(old) == 1
p.write_text(s.replace(old, new))
PY
edit_step mirrorsync/config.py
edit_step tests/test_config.py
run_step "git stash push -q -- mirrorsync/config.py"
if run_step "python3 -m unittest"; then
  echo "good-stash-steps.sh: the suite should fail with the fix stashed" >&2
  exit 1
fi
run_step "git stash pop -q"
run_step "python3 -m unittest"

cat > "$TRIAL_JOB_DIR/final-0.md" <<'MSG'
Fixed `_section_name` to strip before the emptiness check and added `test_blank_section_header`. With the fix stashed the new test fails (ConfigError not raised); with it restored the whole suite passes.
MSG
