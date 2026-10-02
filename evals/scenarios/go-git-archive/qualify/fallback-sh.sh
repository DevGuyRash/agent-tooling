# Launcher with a fallback (must fail): git archive run through sh -c, and git run directly only when sh cannot
# be started, so it is right in both the ordinary and the minimal root; the recorded root notes the sh.
set -eu
. "$TRIAL_SCENARIO_DIR/qualify/common.sh"
apply fallback-sh
finish "tarball: release tarball and SHA256SUMS" "Added \`shipkit tarball\`."
