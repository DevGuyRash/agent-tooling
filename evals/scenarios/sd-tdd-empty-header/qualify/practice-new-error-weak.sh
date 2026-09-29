# Reference behavior (correct outcome, weak practice; passes the required checks): the correct fix with a new
# ConfigError subclass, but the test only checks the literal "[]". It fails against the original parser, yet
# only because the original raises plain ConfigError there; it never exercises a whitespace-only header, so it
# does not guard the gap.
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
        raise BlankSectionError(lineno, "empty section header")
    return name
'''
assert s.count(old) == 1
s = s.replace(old, new)
anchor = "\n\ndef load(path):"
assert s.count(anchor) == 1
s = s.replace(anchor, '''


class BlankSectionError(ConfigError):
    """A section header names no section."""
''' + anchor)
p.write_text(s)
PY
cat > tests/test_blank_section.py <<'PY'
import unittest

from mirrorsync.config import BlankSectionError, parse


class BlankSectionHeaderTest(unittest.TestCase):
    def test_empty_header_raises_blank_section_error(self):
        with self.assertRaises(BlankSectionError):
            parse("[]\n")


if __name__ == "__main__":
    unittest.main()
PY
python3 -m unittest -q 2>/dev/null

cat > "$TRIAL_JOB_DIR/final-0.md" <<'MSG'
Empty section headers now raise `BlankSectionError` (a `ConfigError` subclass): `_section_name` strips the name before checking it. Added `tests/test_blank_section.py`, which fails on the old code and passes now; the full suite passes.
MSG
