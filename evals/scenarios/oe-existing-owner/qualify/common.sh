# Shared by the reference behaviors: apply one of the patches in qualify/patches to the fixture's tree (each is the
# whole change a reference makes, as a diff against the fixture) and run the repository's own check, as an agent would.
# Usage: . common.sh; apply NAME
Q="$TRIAL_SCENARIO_DIR/qualify"
apply() {
  git apply "$Q/patches/$1.patch"
  make check >/dev/null
}
