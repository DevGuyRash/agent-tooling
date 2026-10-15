# Adversarial (must fail no_interface_classes only): an abstract Exporter with a CSV and a text subclass, picked with a conditional.
set -e
. "$TRIAL_SCENARIO_DIR/qualify/common.sh"
apply adv-abc
