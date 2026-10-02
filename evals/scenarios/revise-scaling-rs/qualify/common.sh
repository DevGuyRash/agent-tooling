# Shared by the reference behaviors: lay solution files over the working tree (a solution's Cargo.toml.in
# becomes Cargo.toml, as setup.sh renames the fixture's) and write a final message. Nothing here builds or
# runs cargo, so these arms need no toolchain; the check builds everything.
Q="$TRIAL_SCENARIO_DIR/qualify"
apply() {
  for d in "$@"; do
    cp -R "$d/." .
  done
  for m in $(find . -name Cargo.toml.in -not -path "./.git/*"); do
    mv "$m" "${m%.in}"
  done
}
finish() {
  printf '%s\n' "$1" > "$TRIAL_JOB_DIR/final-0.md"
}
