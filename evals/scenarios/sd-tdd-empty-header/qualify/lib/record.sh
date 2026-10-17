# Sourced by the reference behaviors: run or record a step and add it to the run's record (see record.py).
# edit_step PATH reports an edit the script just made (PATH relative to the repo).
# run_step CMD runs CMD, records it with its real output and exit status, and returns that status;
# run_step_outcome CMD records only whether it succeeded, as some executors' records give.
# The steps edit files and rerun Python within the same second; a same-size edit (git stash pop restoring a
# fix that only moves .strip(), say) then leaves valid-looking stale bytecode, so none is written.
export PYTHONDONTWRITEBYTECODE=1
_record() { python3 "$TRIAL_SCENARIO_DIR/qualify/lib/record.py" "$@"; }
edit_step() { _record edit "$PWD/$1"; }
run_step() {
  _out="$(sh -c "$1" 2>&1)" && _rc=0 || _rc=$?
  _record command "$1" "$_out" "$_rc"
  return "$_rc"
}
run_step_outcome() {
  _out="$(sh -c "$1" 2>&1)" && _rc=0 || _rc=$?
  RECORD_OUTCOME_ONLY=1 _record command "$1" "$_out" "$_rc"
  return "$_rc"
}
