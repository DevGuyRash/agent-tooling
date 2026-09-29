# Sourced by the reference behaviors: run or record a step and report it as agent events on stdout.
# codex_edit PATH / claude_edit PATH TOOL report an edit the script just made (PATH relative to the repo).
# codex_run CMD / claude_run CMD run CMD, report it with its real output and exit status, and return that status.
# The steps edit files and rerun Python within the same second; a same-size edit (git stash pop restoring a
# fix that only moves .strip(), say) then leaves valid-looking stale bytecode, so none is written.
export PYTHONDONTWRITEBYTECODE=1
_event() { python3 "$TRIAL_SCENARIO_DIR/qualify/lib/event.py" "$@"; }
codex_edit() { _event codex-edit "$PWD/$1"; }
claude_edit() { _event claude-edit "$PWD/$1" "$2"; }
codex_run() {
  _out="$(sh -c "$1" 2>&1)" && _rc=0 || _rc=$?
  _event codex-run "$1" "$_out" "$_rc"
  return "$_rc"
}
claude_run() {
  _out="$(sh -c "$1" 2>&1)" && _rc=0 || _rc=$?
  _event claude-run "$1" "$_out" "$_rc"
  return "$_rc"
}
