# Must pass: git archive -o writes the file, which is then hashed; the newest release from git's own version sort.
set -e
. "$TRIAL_SCENARIO_DIR/qualify/common.sh"
apply good-output
finish "tarball: release tarball and SHA256SUMS" "Added \`shipkit tarball\` using git archive -o."
