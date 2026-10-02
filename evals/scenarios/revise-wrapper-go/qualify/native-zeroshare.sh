# Native but wrong: a route where nothing ran gets a share of 0 (the plain guard against dividing by zero) instead
# of coming first, so a route whose every sailing that ran was late, seen earlier, is listed before it. Passes the
# fixture's tests; fails the hidden zero-share case in every root.
set -e
sh "$TRIAL_SCENARIO_DIR/qualify/native.sh"
python3 - <<'PY'
from pathlib import Path
p = Path("cmd/ferry/figures.go")
s = p.read_text()
old = """	if ran == 0 {
		return -1
	}"""
assert s.count(old) == 1
p.write_text(s.replace(old, """	if ran == 0 {
		return 0
	}"""))
PY
git commit -q -am "punctuality: share 0 when nothing ran"
