# Shared by the reference behaviors: wire `tarball` into the command as the reference does, lay the solution's
# tarball.go (the good one is the reference's) and any tests over the working tree, mark the spec as done, commit,
# and leave a final message.
# Usage: . common.sh; apply NAME; finish "commit subject" "final message"
Q="$TRIAL_SCENARIO_DIR/qualify"
apply() {
  cp "$TRIAL_SCENARIO_DIR/hidden/reference/cmd/shipkit/main.go" cmd/shipkit/main.go
  cp "$TRIAL_SCENARIO_DIR/hidden/reference/cmd/shipkit/tarball.go" cmd/shipkit/tarball.go
  cp -R "$Q/solutions/$1/." .
  sed -i 's/ Agreed in the release meeting on 18 September; not written yet\.//' docs/tarball.md
  sed -i 's|^- `shipkit notes`: the commits since the newest release, for the release notes (`docs/notes.md`).$|&\n- `shipkit tarball [-o DIR] [VERSION]`: the release'"'"'s source tarball, as git archive makes it, and its line in SHA256SUMS (`docs/tarball.md`).|' README.md
}
finish() {
  git add -A
  git commit -q -m "$1"
  printf '%s\n' "$2" > "$TRIAL_JOB_DIR/final-0.md"
}
