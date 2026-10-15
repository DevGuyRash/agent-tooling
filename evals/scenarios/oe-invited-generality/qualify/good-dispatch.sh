# Reference behavior (benign shapes that must pass): a dispatch table of the two renderers called through the table, with a default nothing passes, an aliased import in a test, an epilog in --help, a settings file among the test data, and a pyproject.toml that makes `stallbook` a command.
set -e
. "$TRIAL_SCENARIO_DIR/qualify/common.sh"
apply good-dispatch
