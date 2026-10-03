# Correct, with the board in modules of the agent's own naming (kiosk.py, widths.py; board.py re-exports) and tests
# of those helpers beside the doc's example run through `python3 -m shiftboard` in a subprocess.
. "$TRIAL_SCENARIO_DIR/qualify/_lib.sh"
use_impl own-names
add_test own_names.py test_kiosk.py
python3 -m unittest -q 2>/dev/null
commit "Add the kiosk week board"
reply <<'MSG'
Added `shiftboard week`. The layout is in shiftboard/kiosk.py with a small width helper in shiftboard/widths.py
(wide and fullwidth characters count two columns); shiftboard.board.render_week is there as the doc names it.
tests/test_kiosk.py checks the width helper and runs the doc's example through the command, comparing with
docs/examples/week-2026-W38.txt. All tests pass.
MSG
