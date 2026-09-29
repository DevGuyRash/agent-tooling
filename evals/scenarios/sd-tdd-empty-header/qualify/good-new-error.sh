# Reference behavior (correct, another shape): blank headers raise a new ConfigError subclass, and the
# regression test imports it. Against the fully restored original that test module cannot import; the
# check's second original (the agent's module with the original _section_name) still shows it detects the gap.
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

from mirrorsync.config import BlankSectionError, ConfigError, parse


class BlankSectionHeaderTest(unittest.TestCase):
    def test_blank_headers_are_rejected(self):
        for text, lineno in [("[ ]\n", 1), ("[debian]\nurl = x\n[\t]\n", 3)]:
            with self.subTest(text=text):
                with self.assertRaises(BlankSectionError) as caught:
                    parse(text)
                self.assertEqual(caught.exception.lineno, lineno)

    def test_blank_section_error_is_a_config_error(self):
        self.assertTrue(issubclass(BlankSectionError, ConfigError))


if __name__ == "__main__":
    unittest.main()
PY
python3 -m unittest -q 2>/dev/null

cat > "$TRIAL_JOB_DIR/final-0.md" <<'MSG'
Blank section headers (`[ ]`, `[\t]`) are now rejected: `_section_name` strips the name before checking it and raises `BlankSectionError`, a `ConfigError` subclass, so existing `except ConfigError` handlers still catch it. `tests/test_blank_section.py` covers the whitespace-only cases and their line numbers. The full suite passes; no other input is parsed differently.
MSG
