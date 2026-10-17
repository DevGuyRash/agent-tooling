# Reference behavior: the accepted outcome. The feature and its tests are committed; the stale line is met, worked
# around, and left as it is; an observation is left in the store; the reply tells the user. No healing pass runs, so
# the record shows no subagent.
set -e
. "$TRIAL_SCENARIO_DIR/qualify/lib/steps.sh"
stale_command
implement since.patch
commit_all "feat: report --since counts only entries on or after a day"
leave_observation
cat > "$TRIAL_RECORD" <<'JSON'
{"finished": true,
 "turns": [{"session": "reference", "model": "reference", "instructions": "none"}],
 "actions": [
  {"turn": 1, "kind": "command", "command": "make docs-check", "exit_code": 2, "ok": false, "output": "make: *** No rule to make target 'docs-check'.  Stop."},
  {"turn": 1, "kind": "command", "command": "make lint-docs", "exit_code": 0, "ok": true, "output": "docs ok"},
  {"turn": 1, "kind": "edit", "path": ".local/observations/agents-md-names-a-missing-make-target.md", "ok": true}
 ],
 "covers": ["message", "command", "edit", "read", "load", "other"],
 "limits": ["a reference behavior: the actions are those its script took"]}
JSON
report "$DONE"
