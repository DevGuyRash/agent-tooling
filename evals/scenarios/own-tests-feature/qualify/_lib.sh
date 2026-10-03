# Sourced by the reference behaviors: copy a reference implementation or test file into the working tree,
# commit, and write the final reply.
set -e
Q="$TRIAL_SCENARIO_DIR/qualify/solutions"
use_impl() { cp "$Q/$1/shiftboard/"*.py shiftboard/; }
add_test() { cp "$Q/tests/$1" "tests/$2"; }
commit() { git add -A && git commit -qm "$1"; }
reply() { cat > "$TRIAL_JOB_DIR/final-0.md"; }
