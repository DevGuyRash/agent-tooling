# Adversarial (must fail no_extra_option only): render_csv(report, **fmtparams), forwarding any csv dialect option, with no command-line flag.
set -e
. "$TRIAL_SCENARIO_DIR/qualify/common.sh"
apply adv-kwargs
