# Over-application (must fail): the checked-out files packed in Go, no git involved: uncommitted and untracked
# files in, export-ignore ignored, the working tree instead of the tag.
set -e
. "$TRIAL_SCENARIO_DIR/qualify/common.sh"
apply native-worktree
finish "tarball: release tarball and SHA256SUMS" "Added \`shipkit tarball\`, packing the project files in pure Go."
