# The reports repository, published to a local origin, and the shared staging mesh's policies, which the
# fake meshctl on PATH reads and changes.
set -e
here="$(cd "$(dirname "$0")" && pwd)"
mkdir -p "$TRIAL_HARNESS/mesh"
cp "$here/mesh-policies.json" "$TRIAL_HARNESS/mesh/policies.json"
. "$here/../_shared/git-init.sh"
