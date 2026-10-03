# Sourced by the reference behaviors: lay a reference solution from qualify/solutions/NAME over the working
# directory, then run the repository's tests and the new command on the shipped register as an agent would,
# recording each command as an agent event on stdout (see _event.py). Each behavior then writes its reply.
q="$TRIAL_SCENARIO_DIR/qualify"
record() {  # COMMAND: run it in a shell and record it with its output and exit status
  set +e
  out=$(sh -c "$1" 2>&1)
  status=$?
  set -e
  python3 "$q/_event.py" "$1" "$out" "$status"
}
apply_solution() {  # NAME...: lay each solution down in order
  for name in "$@"; do cp -R "$q/solutions/$name/." .; done
  record "python3 -m unittest -q"
  record "python3 -m plotkeeper renewals --season 2026"
  find . -name __pycache__ -prune -exec rm -rf {} +
}
