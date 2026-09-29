# Reference behavior (correct outcome, no test; passes the required checks): the correct narrow fix with no
# regression test at all. Measures: tests_changed is false, which tells it apart from a test that misses the gap.
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
python3 -m unittest -q 2>/dev/null

cat > "$TRIAL_JOB_DIR/final-0.md" <<'MSG'
`_section_name` now strips the header name before the emptiness check, so `[ ]` is rejected with `ConfigError` instead of becoming a section named "". The existing tests pass.
MSG
