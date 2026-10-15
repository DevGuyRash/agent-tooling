# Adversarial (must fail no_registry_or_plugins only): Exporter fills a formats dict from __init_subclass__.
set -e
. "$TRIAL_SCENARIO_DIR/qualify/common.sh"
apply adv-subclass-hook
