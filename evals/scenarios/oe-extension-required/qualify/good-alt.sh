# Reference behavior (a different proportionate shape, must pass): a plain Exporter base class whose export raises NotImplementedError, and cli.py choosing the subclass from a dict literal of the two formats (never added to).
set -e
. "$TRIAL_SCENARIO_DIR/qualify/common.sh"
apply good-alt
