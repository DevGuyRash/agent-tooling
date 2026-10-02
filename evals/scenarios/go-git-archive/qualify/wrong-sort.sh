# Must fail: the reference with the newest release taken as the greatest tag name (v1.9.0 over v1.10.0).
set -e
. "$TRIAL_SCENARIO_DIR/qualify/common.sh"
apply wrong-sort
finish "tarball: release tarball and SHA256SUMS" "Added \`shipkit tarball\`."
