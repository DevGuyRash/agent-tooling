# Adversarial (must fail no_extra_format only): CSV, and the roadmap's Excel as a binary format written to standard output's buffer.
set -e
. "$TRIAL_SCENARIO_DIR/qualify/common.sh"
apply adv-xlsx
