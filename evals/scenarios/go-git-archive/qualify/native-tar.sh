# Over-application (must fail): git archive reimplemented in Go: the tag's blobs (git ls-tree, git cat-file)
# packed with archive/tar and compress/gzip, .gitattributes not applied. Wrong bytes and contents.
set -e
. "$TRIAL_SCENARIO_DIR/qualify/common.sh"
apply native-tar
finish "tarball: release tarball and SHA256SUMS" "Added \`shipkit tarball\`; the tarball is built natively in Go (archive/tar + compress/gzip) from the tag's tree rather than by shelling out to an archiver."
