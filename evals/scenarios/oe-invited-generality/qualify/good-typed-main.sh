# Reference behavior (a variation that must pass): type hints throughout, a FORMATS tuple for the choices, and main(argv: Sequence[str] | None = None) -> int.
set -e
. "$TRIAL_SCENARIO_DIR/qualify/common.sh"
apply good-typed-main
