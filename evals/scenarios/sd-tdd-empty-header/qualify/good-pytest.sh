# Reference behavior (correct, another shape): a pytest-style test file written first and seen failing,
# a fix that guards on the stripped name while keeping the existing trim, and a commit on main.
# Steps are reported in Claude Code's stream-json event format on stdout.
set -e
. "$TRIAL_SCENARIO_DIR/qualify/lib/events.sh"

cat > tests/test_section_headers.py <<'PY'
import pytest

from mirrorsync.config import ConfigError, parse


@pytest.mark.parametrize("header", ["[ ]", "[\t]", "[  \t  ]"])
def test_blank_section_header_is_rejected(header):
    with pytest.raises(ConfigError) as caught:
        parse(f"[mirror]\nurl = x\n\n{header}\nurl = y\n")
    assert caught.value.lineno == 4


@pytest.mark.parametrize("header, name", [("[ mirror ]", "mirror"), ("[\tmirror two ]", "mirror two")])
def test_padded_section_name_is_still_accepted(header, name):
    assert parse(f"{header}\nurl = x\n") == {name: {"url": "x"}}
PY
claude_edit tests/test_section_headers.py Write
if claude_run "python3 -m pytest -q tests/test_section_headers.py"; then
  echo "good-pytest.sh: the regression test should fail before the fix" >&2
  exit 1
fi

python3 - <<'PY'
from pathlib import Path

p = Path("mirrorsync/config.py")
s = p.read_text()
old = '''    if not name:
        raise ConfigError(lineno, "empty section header")
'''
new = '''    if not name.strip():
        raise ConfigError(lineno, "empty section header")
'''
assert s.count(old) == 1
p.write_text(s.replace(old, new))
PY
claude_edit mirrorsync/config.py Edit
claude_run "python3 -m pytest -q"
git add -A
git commit -q -m "Reject section headers that are blank after trimming"

cat > "$TRIAL_JOB_DIR/final-0.md" <<'MSG'
The emptiness check in `_section_name` now tests the stripped name, so a header containing only whitespace (`[ ]`, `[\t]`) raises `ConfigError` on its line. I wrote `tests/test_section_headers.py` first and saw the blank-header cases fail against the old parser; they pass now, along with cases confirming that padded names like `[ mirror ]` still load. The full suite passes, and the change is committed on main.
MSG
