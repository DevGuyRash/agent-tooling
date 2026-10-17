# Sourced by the reference behaviors: lay reference solutions from qualify/solutions over the working
# directory, change the integration suite in place with patches.py, and run commands as an agent would,
# adding each one to the run's record (see _record.py; RECORD_OUTCOME_ONLY records only whether it succeeded).
# The fake docker, docker-compose, and podman on PATH log their own calls. Each behavior then writes its
# reply.
q="$TRIAL_SCENARIO_DIR/qualify"
record() {  # COMMAND: run it in a shell and record it with its output and exit status
  set +e
  out=$(sh -c "$1" 2>&1)
  status=$?
  set -e
  python3 "$q/_record.py" command "$1" "$out" "$status"
}
apply_solution() {  # NAME...: lay each solution down in order
  for name in "$@"; do cp -R "$q/solutions/$name/." .; done
}
patch_suite() {  # skip | standin
  python3 "$q/patches.py" "$1"
}
tidy() {
  find . -name __pycache__ -prune -exec rm -rf {} +
}
