# Adversarial (must fail no_registry_or_plugins only): cli.py finds the Exporter subclasses by looking through vars(exporters).
set -e
. "$TRIAL_SCENARIO_DIR/qualify/common.sh"
apply adv-vars-discovery
