# Reference behavior (a different proportionate shape, must pass): the same render_csv, with cli.py choosing the renderer from a dict literal of the two formats (a dispatch table, never added to), and its test in the existing test_cli.py.
set -e
. "$TRIAL_SCENARIO_DIR/qualify/common.sh"
apply good-alt
