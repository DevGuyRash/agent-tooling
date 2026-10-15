# Adversarial (must fail interface_ok only): Exporter also carries a media_type, an extension, filename(), and export_bytes() with defaults, so a subclass with only export still builds.
set -e
. "$TRIAL_SCENARIO_DIR/qualify/common.sh"
apply adv-heavy-concrete
