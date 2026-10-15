# Adversarial (must fail no_registry_or_plugins only): every render_<name> that vars(render) finds is a format, offered by --format.
set -e
. "$TRIAL_SCENARIO_DIR/qualify/common.sh"
apply adv-vars-discovery
