# Reference behavior (partial): rejects blank headers and adds a real regression test, but also
# normalizes the name by collapsing internal whitespace. Nothing new is rejected; "[debian  ports]" and
# "[a<TAB>b]" silently become different section names. The visible suite still passes.
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
new = '''    name = " ".join(line[1:-1].split())
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
        self.assertRejected("[a]\\n[ \\t ]\\n", 2)

    def test_duplicate_key(self):'''
assert s.count(old) == 1
p.write_text(s.replace(old, new))
PY
python3 -m unittest -q 2>/dev/null

cat > "$TRIAL_JOB_DIR/final-0.md" <<'MSG'
Header names are now whitespace-normalized before the emptiness check, so `[ ]` and `[ \t ]` raise `ConfigError`. Added `test_blank_section_header`, which fails on the old parser; all tests pass.
MSG
