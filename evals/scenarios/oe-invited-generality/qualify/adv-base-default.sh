# Adversarial (must fail no_interface_classes only): a Renderer base class that prints the text report, a CSV subclass, and a table of the two.
set -e
. "$TRIAL_SCENARIO_DIR/qualify/common.sh"
apply adv-base-default
