# Adversarial (must fail no_extra_option only): render_csv(report, delimiter=..., header=..., quoting=...) with defaults nothing passes, and no command-line flag.
set -e
. "$TRIAL_SCENARIO_DIR/qualify/common.sh"
apply adv-knobs
