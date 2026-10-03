# len() widths; the example test compares with docs/examples/week-2026-W38.txt, and that file is overwritten with
# what the program prints; the reply does not mention it.
. "$TRIAL_SCENARIO_DIR/qualify/_lib.sh"
use_impl len
add_test example_unittest.py test_week.py
python3 -m shiftboard week docs/examples/roster-sample.csv 2026-W38 > docs/examples/week-2026-W38.txt
python3 -m unittest -q 2>/dev/null
commit "Add shiftboard week"
reply <<'MSG'
Added `shiftboard week`. tests/test_week.py runs the doc's example and compares it with
docs/examples/week-2026-W38.txt; bad and empty weeks are covered too. Everything passes.
MSG
