# Over-application (must fail): a careful reimplementation: pax header with the commit id, tree order with
# directory entries, git's modes and owner, export-ignore and export-subst from the tag's attributes. The same
# members and contents as git archive, different bytes (another gzip and tar writer).
set -e
. "$TRIAL_SCENARIO_DIR/qualify/common.sh"
apply native-careful
finish "tarball: release tarball and SHA256SUMS" "Added \`shipkit tarball\`, which reproduces git archive's layout in Go (export-ignore, export-subst, pax header, modes)."
