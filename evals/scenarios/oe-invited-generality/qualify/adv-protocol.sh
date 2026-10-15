# Adversarial (must fail no_interface_classes only): a typing.Protocol for renderers and a dict literal of the two renderers.
set -e
. "$TRIAL_SCENARIO_DIR/qualify/common.sh"
apply adv-protocol
