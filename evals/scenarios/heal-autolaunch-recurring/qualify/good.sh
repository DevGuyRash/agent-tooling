# Reference behavior: the accepted outcome, the healing pass run in a fresh subagent. The feature and its tests are
# committed; a pass started on the recurrence corrects AGENTS.md in place and closes the observation; the reply reports
# it. The record is the one such a run leaves: the pass's actions carry the subagent that took them.
set -e
. "$TRIAL_SCENARIO_DIR/qualify/lib/steps.sh"
stale_command
implement since.patch
commit_all "feat: report --since counts only entries on or after a day"
heal_and_close
cat > "$TRIAL_RECORD" <<'JSON'
{"finished": true,
 "turns": [{"session": "reference", "model": "reference", "instructions": "none"}],
 "actions": [
  {"turn": 1, "kind": "command", "command": "make docs-check", "exit_code": 2, "ok": false, "output": "make: *** No rule to make target 'docs-check'.  Stop."},
  {"turn": 1, "kind": "command", "command": "make lint-docs", "exit_code": 0, "ok": true, "output": "docs ok"},
  {"turn": 1, "kind": "other", "name": "Agent", "ok": true, "output": "healing pass started on the stale AGENTS.md instruction"},
  {"turn": 1, "kind": "edit", "path": "AGENTS.md", "ok": true, "agent": "healing-pass"},
  {"turn": 1, "kind": "command", "command": "rm .local/observations/agents-md-names-a-missing-make-target.md", "exit_code": 0, "ok": true, "agent": "healing-pass"}
 ],
 "covers": ["message", "command", "edit", "read", "load", "other"],
 "limits": ["a reference behavior: the actions are those its script took, the pass's attributed to a subagent"]}
JSON
report "$DONE" "Nothing else changed."
