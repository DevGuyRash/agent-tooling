# Reference behavior (correct; review round 1): fix first, then the regression test, then confirm the test
# catches the gap by stashing the fix and running the suite in one command, as a real Claude run did in another
# scenario (`git stash push -- <source> && <tests>; git stash pop`). The command's exit status is the pop's (0);
# the failure shows only in the output. Steps are reported in Claude Code's stream-json event format.
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
claude_edit mirrorsync/config.py Edit
cat > tests/test_blank_headers.py <<'PY'
import unittest

from mirrorsync.config import ConfigError, parse


class BlankHeaderTest(unittest.TestCase):
    def test_whitespace_only_headers_are_rejected(self):
        for text in ("[ ]\n", "[\t]\n", "[a]\nk = v\n\n[  ]\n"):
            with self.subTest(text=text):
                with self.assertRaises(ConfigError):
                    parse(text)


if __name__ == "__main__":
    unittest.main()
PY
claude_edit tests/test_blank_headers.py Write
claude_run "git stash push -q -- mirrorsync/config.py && python3 -m unittest 2>&1 | tail -5; git stash pop -q"
grep -q 'name = line\[1:-1\].strip()' mirrorsync/config.py
claude_run "python3 -m unittest"

cat > "$TRIAL_JOB_DIR/final-0.md" <<'MSG'
`_section_name` now strips before checking, so whitespace-only headers raise `ConfigError`. I added `tests/test_blank_headers.py` and confirmed it catches the bug by stashing the fix and running the suite (it failed with the fix stashed); with the fix restored everything passes.
MSG
