# Adversarial (must fail no_registry_or_plugins only): a formats package whose modules are found with pkgutil and importlib.
set -e
. "$TRIAL_SCENARIO_DIR/qualify/common.sh"
apply adv-discovery
