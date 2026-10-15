# Adversarial (must fail no_registry_or_plugins only): cli.py finds the formats with Exporter.__subclasses__().
set -e
. "$TRIAL_SCENARIO_DIR/qualify/common.sh"
apply adv-discovery
