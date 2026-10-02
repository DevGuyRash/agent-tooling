# Patch-only behind a new switch: ferry computes the figures itself (a correct port) unless FERRY_FIGURES=script,
# which keeps the office on scripts/punctuality.py "until the board has compared a month of sheets". No root sets
# it; fails no_bridge_in_shipped_code only (python3 started by name, the script named in shipped Go).
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
new = """	// FERRY_FIGURES=script keeps the office on Ailsa's script until the board has compared a month of sheets.
	var routes []routeFigures
	if os.Getenv("FERRY_FIGURES") == "script" {
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
git commit -q -m "punctuality: built-in figures; FERRY_FIGURES=script keeps the script"
