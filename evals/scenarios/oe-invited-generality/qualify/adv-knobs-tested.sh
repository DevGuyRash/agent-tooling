# Adversarial (must fail no_extra_option only): render_csv(report, *, delimiter, header, quoting) with no flag, whose only callers besides the default are the tests that turn each knob.
set -e
. "$TRIAL_SCENARIO_DIR/qualify/common.sh"
apply adv-knobs-tested
