# Correct, with pytest-style tests: the doc's example through main with capsys, parametrized bad weeks, wide names
# with tmp_path, and a plain function. Needs pytest on the host.
. "$TRIAL_SCENARIO_DIR/qualify/_lib.sh"
use_impl good
add_test example_pytest.py test_week_board.py
python3 -m pytest -q -p no:cacheprovider >/dev/null
commit "Add shiftboard week"
reply <<'MSG'
`shiftboard week` is implemented per docs/board.md. Tests are in tests/test_week_board.py (pytest): the doc's
example compared with docs/examples/week-2026-W38.txt, bad weeks, Chinese names lining up, and an empty week.
`python3 -m pytest` passes, including the existing unittest tests.
MSG
