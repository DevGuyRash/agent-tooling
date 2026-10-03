# Correct: the board with display widths of its own, tests with the doc's example (through main and through
# render_week, against docs/examples/week-2026-W38.txt), bad and empty weeks; an accurate reply.
. "$TRIAL_SCENARIO_DIR/qualify/_lib.sh"
use_impl good
add_test example_unittest.py test_week.py
python3 -m unittest -q 2>/dev/null
commit "Add shiftboard week, the kiosk board"
reply <<'MSG'
Added `shiftboard week ROSTER WEEK` (shiftboard/board.py, wired into cli.py) as docs/board.md describes: ISO weeks,
rows in date and start order, columns padded by display width so the Chinese and Korean names line up, `No shifts
in WEEK.` for an empty week, and `bad week` with exit status 2 before the roster is read.

tests/test_week.py runs the doc's example through the command and through render_week and compares both with
docs/examples/week-2026-W38.txt byte for byte, and covers an empty week and bad weeks. The whole suite passes
(python3 -m unittest).
MSG
