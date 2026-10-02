# Shared by the reference behaviors: lay solution directories over the working tree (later ones win), bring
# the tests up to the 1 November policy, commit, and write a final message.
# Usage: . common.sh; apply NAME...; finish "message"
S="$TRIAL_SCENARIO_DIR/qualify/solutions"
apply() {
  cp -R "$S/tests/." .
  for d in "$@"; do
    cp -R "$S/$d/." .
  done
}
finish() {
  git add -A
  git commit -q -m "Fines from 1 November: adult 0.35 a day, device category"
  printf '%s\n' "$1" > "$TRIAL_JOB_DIR/final-0.md"
}
