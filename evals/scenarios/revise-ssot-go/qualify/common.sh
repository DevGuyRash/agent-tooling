# Shared by the reference behaviors: lay solution directories over the working tree (later ones win), bring
# the tests up to the 2027/28 charges, commit, and write a final message.
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
  git commit -q -m "2027/28 permit charges: band G, diesel surcharge 45.00"
  printf '%s\n' "$1" > "$TRIAL_JOB_DIR/final-0.md"
}
