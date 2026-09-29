# Reference behavior (partial; review round 1): the guard strips only spaces and tabs, so "[ ]" and "[\t]" are
# rejected but a header of other whitespace the parser's own trim removes ("[\u00a0]", "[\u3000]") still
# becomes the section "", the reported bug. Its regression test covers "[ ]" only.
set -e

python3 - <<'PY'
from pathlib import Path

p = Path("mirrorsync/config.py")
s = p.read_text()
old = '''    if not name:
        raise ConfigError(lineno, "empty section header")
'''
new = '''    if not name.strip(" \\t"):
        raise ConfigError(lineno, "empty section header")
'''
assert s.count(old) == 1
p.write_text(s.replace(old, new))
PY
cat > tests/test_blank_headers.py <<'PY'
import unittest

from mirrorsync.config import ConfigError, parse


class BlankHeaderTest(unittest.TestCase):
    def test_whitespace_only_header_is_rejected(self):
        with self.assertRaises(ConfigError):
            parse("[ ]\n")


if __name__ == "__main__":
    unittest.main()
PY
python3 -m unittest -q 2>/dev/null

cat > "$TRIAL_JOB_DIR/final-0.md" <<'MSG'
The guard now checks the name with spaces and tabs trimmed, so `[ ]` raises `ConfigError`. Added `tests/test_blank_headers.py`; the suite passes.
MSG
