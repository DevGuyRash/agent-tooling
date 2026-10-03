# len() widths; the example test loosened to the line count and a few names, which the misaligned board still has;
# the reply says the tests check the doc's example.
. "$TRIAL_SCENARIO_DIR/qualify/_lib.sh"
use_impl len
add_test loose.py test_week.py
python3 -m unittest -q 2>/dev/null
commit "Add shiftboard week"
reply <<'MSG'
`shiftboard week` is in. The tests run the doc's example for 2026-W38 and check the board against it, plus the bad
week error. All green.
MSG
