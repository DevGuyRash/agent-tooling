# Sourced by the reference behaviors: lay a reference solution from qualify/solutions/NAME over the working
# directory and run commands as an agent would, adding each one to the run's record (see
# _record.py). Each behavior then writes its reply.
q="$TRIAL_SCENARIO_DIR/qualify"
record() {  # COMMAND: run it in a shell and record it with its output and exit status
  set +e
  out=$(sh -c "$1" 2>&1)
  status=$?
  set -e
  python3 "$q/_record.py" command "$1" "$out" "$status"
}
apply_solution() {
  cp -R "$q/solutions/$1/." .
}
tidy() {
  find . -name __pycache__ -prune -exec rm -rf {} +
}
