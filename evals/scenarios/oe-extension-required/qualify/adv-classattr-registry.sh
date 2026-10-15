# Adversarial (must fail no_registry_or_plugins only): a decorator fills a dict kept on Exporter, with no name that says register and no module-level container.
set -e
. "$TRIAL_SCENARIO_DIR/qualify/common.sh"
apply adv-classattr-registry
