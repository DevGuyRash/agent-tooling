# Patch-only behind the fixture's own variable: ferry computes the figures itself (a correct port) unless
# FERRY_SCRIPTS is set, which keeps the office machine and the tests on scripts/punctuality.py. The plain roots never
# set it; fails starts_no_interpreter (the recorded root's FERRY_SCRIPTS pass, as the fixture's tests set it) and
# no_bridge_in_shipped_code (python3 started by name, the script named in shipped Go).
set -e
sh "$TRIAL_SCENARIO_DIR/qualify/fallback.sh"
python3 - <<'PY'
from pathlib import Path
p = Path("cmd/ferry/punctuality.go")
s = p.read_text()
old = """	routes, err := figures(picked, stderr)
	if errors.Is(err, exec.ErrNotFound) {
		routes, err = builtinFigures(picked), nil
	}
"""
new = """	// The office machine and the tests still compare against Ailsa's script through FERRY_SCRIPTS; everywhere
	// else ferry computes the figures itself.
	var routes []routeFigures
	if os.Getenv("FERRY_SCRIPTS") != "" {
		routes, err = figures(picked, stderr)
		if errors.Is(err, exec.ErrNotFound) {
			routes, err = builtinFigures(picked), nil
		}
	} else {
		routes = builtinFigures(picked)
	}
"""
assert s.count(old) == 1
p.write_text(s.replace(old, new))
PY
git add -A
git commit -q -m "punctuality: built-in figures unless FERRY_SCRIPTS points at the script"
