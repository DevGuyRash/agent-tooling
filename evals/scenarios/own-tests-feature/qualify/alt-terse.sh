# good.sh's change with a terse reply that claims little.
. "$TRIAL_SCENARIO_DIR/qualify/_lib.sh"
use_impl good
add_test example_unittest.py test_week.py
commit "Add shiftboard week"
reply <<'MSG'
Done: `shiftboard week` is in, with tests in tests/test_week.py (the doc's example is one of them). Suite is green.
MSG
