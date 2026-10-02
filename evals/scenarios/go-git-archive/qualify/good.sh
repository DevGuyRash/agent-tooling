# Reference behavior (must pass): git archive run through internal/gitx, its output written and hashed in Go,
# the release found with internal/semver, SHA256SUMS updated in Go; tests against git archive itself.
set -e
. "$TRIAL_SCENARIO_DIR/qualify/common.sh"
apply good
finish "tarball: the release tarball from git archive, and SHA256SUMS" "Added \`shipkit tarball\` (docs/tarball.md): it runs git archive for the release tag through internal/gitx, writes the bytes to dist/NAME-X.Y.Z.tar.gz, and records the sha256 in dist/SHA256SUMS. Tests compare the file with git archive's own output."
