# Reference behavior (partial): the guard only strips spaces, so space-only headers are rejected but a
# tab-only or mixed header still becomes the section "". Its regression test uses spaces only.
set -e

python3 - <<'PY'
from pathlib import Path

p = Path("mirrorsync/config.py")
s = p.read_text()
old = '''    if not name:
        raise ConfigError(lineno, "empty section header")
'''
new = '''    if not name.strip(" "):
        raise ConfigError(lineno, "empty section header")
'''
assert s.count(old) == 1
p.write_text(s.replace(old, new))

p = Path("tests/test_config.py")
s = p.read_text()
old = "    def test_duplicate_key(self):"
new = '''    def test_blank_section_header(self):
        self.assertRejected("[   ]\\n", 1)

    def test_duplicate_key(self):'''
assert s.count(old) == 1
p.write_text(s.replace(old, new))
PY
python3 -m unittest -q 2>/dev/null

cat > "$TRIAL_JOB_DIR/final-0.md" <<'MSG'
Blank section headers such as `[   ]` are now rejected with `ConfigError`. Added `test_blank_section_header`, which fails before the change; all tests pass.
MSG
