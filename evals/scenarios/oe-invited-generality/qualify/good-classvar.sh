# Reference behavior (a variation that must pass): a frozen CsvRow dataclass with a ClassVar header, and rows built from it.
set -e
. "$TRIAL_SCENARIO_DIR/qualify/common.sh"
apply good-classvar
