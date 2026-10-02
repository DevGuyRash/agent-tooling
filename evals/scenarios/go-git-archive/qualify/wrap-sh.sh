# Launcher (must fail): git archive run through sh -c with its output captured; wrong only where no shell exists.
set -e
. "$TRIAL_SCENARIO_DIR/qualify/common.sh"
apply wrap-sh
finish "tarball: release tarball and SHA256SUMS" "Added \`shipkit tarball\`."
