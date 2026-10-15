# Adversarial (must fail no_interface_classes only): a plain Exporter base class whose method raises NotImplementedError, no abc.
set -e
. "$TRIAL_SCENARIO_DIR/qualify/common.sh"
apply adv-stub-base
