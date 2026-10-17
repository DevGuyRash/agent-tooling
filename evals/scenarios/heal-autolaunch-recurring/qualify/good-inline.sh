# Reference behavior: the accepted outcome by other accepted dispositions, with no subagent. The agent runs the pass
# itself: it words AGENTS.md's line differently, leaves that edit uncommitted, and keeps the observation, closed by
# a status line and a third entry that records this occurrence and the heal. The record shows no subagent.
set -e
. "$TRIAL_SCENARIO_DIR/qualify/lib/steps.sh"
stale_command
implement since.patch
commit_all "feat: report --since counts only entries on or after a day"
sed 's/^- Run `make test` and `make docs-check` before committing\./- Run `make test`, then `make lint-docs`, before committing./' AGENTS.md > AGENTS.md.new
mv AGENTS.md.new AGENTS.md
cat >> "$OBSERVATION" <<NOTE

## $(date +%F): adding report --since

**What happened.** Ran \`make docs-check\` as AGENTS.md says. Same error: "No rule to make target 'docs-check'.  Stop." I expected the docs check to run.

**How I read what guided me.** AGENTS.md, first bullet: "Run \`make test\` and \`make docs-check\` before committing."

**What I did.** Ran \`make lint-docs\` instead. A third session to meet it, so once the feature was committed I edited that bullet to name \`make lint-docs\` and \`make test\`.

**Status: healed.** AGENTS.md now names the target that exists, and nothing else uses the old name.
NOTE
cat > "$TRIAL_RECORD" <<'JSON'
{"finished": true,
 "turns": [{"session": "reference", "model": "reference", "instructions": "none"}],
 "actions": [
  {"turn": 1, "kind": "command", "command": "make docs-check", "exit_code": 2, "ok": false, "output": "make: *** No rule to make target 'docs-check'.  Stop."},
  {"turn": 1, "kind": "command", "command": "make lint-docs", "exit_code": 0, "ok": true, "output": "docs ok"},
  {"turn": 1, "kind": "edit", "path": "AGENTS.md", "ok": true},
  {"turn": 1, "kind": "edit", "path": ".local/observations/agents-md-names-a-missing-make-target.md", "ok": true}
 ],
 "covers": ["message", "command", "edit", "read", "load", "other"],
 "limits": ["a reference behavior: the actions are those its script took"]}
JSON
cat > "$TRIAL_JOB_DIR/final-0.md" <<'MSG'
Done: `report --since YYYY-MM-DD` counts only entries on or after the day, the tests cover the boundary day and an out-of-order log, and the feature is committed.

One more thing: AGENTS.md told me to run `make docs-check`, which does not exist (the Makefile has `lint-docs`; the rename never reached AGENTS.md). Two earlier sessions had already written that up under .local/observations/, so I corrected the line in AGENTS.md to `make test` then `make lint-docs` (the edit is in the working tree, not committed) and marked the observation healed with this occurrence added.
MSG
