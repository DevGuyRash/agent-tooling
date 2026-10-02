# Shared by the reference behaviors: lay solution files over the working tree, run the tests, and write a
# final message.
Q="$TRIAL_SCENARIO_DIR/qualify"
apply() {
  for d in "$@"; do
    cp -R "$d/." .
  done
}
finish() {
  node --test >"$TRIAL_JOB_DIR/own-tests.log" 2>&1 || true
  printf '%s\n' "$1" > "$TRIAL_JOB_DIR/final-0.md"
}
