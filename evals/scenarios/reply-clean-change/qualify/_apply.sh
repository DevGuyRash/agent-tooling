# Sourced by the reference behaviors: lay a reference solution from qualify/solutions/NAME over the working
# directory and run commands as an agent would, recording each one as an agent event on stdout (see
# _event.py). Each behavior then writes its reply.
q="$TRIAL_SCENARIO_DIR/qualify"
record() {  # COMMAND: run it in a shell and record it with its output and exit status
  set +e
  out=$(sh -c "$1" 2>&1)
  status=$?
  set -e
  python3 "$q/_event.py" "$1" "$out" "$status"
}
apply_solution() {
  cp -R "$q/solutions/$1/." .
}
tidy() {
  find . -name __pycache__ -prune -exec rm -rf {} +
}
