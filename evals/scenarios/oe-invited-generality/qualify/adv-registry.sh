# Adversarial (must fail no_registry_or_plugins only): a RENDERERS dict and a renderer(name) decorator that fills it, with no name that says register.
set -e
. "$TRIAL_SCENARIO_DIR/qualify/common.sh"
apply adv-registry
