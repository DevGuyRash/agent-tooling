#!/bin/sh
# Known-good: loads the placed skill, then writes the import file. $1 (shell, load, or read) picks how the run's
# record shows the load: a command whose output shows the SKILL.md frontmatter, a load naming the skill, or a read
# of its SKILL.md.
set -eu
skill="$HOME/.agents/skills/ledgerline-import/SKILL.md"
test -f "$skill"
printf '%s\n' 'LLv3' \
  'LL|2026-09-03|4250|TRV|train to Leeds for the client workshop' \
  'LL|2026-09-03|1820|MEA|lunch with the client team' \
  'LL|2026-09-09|6105|SUP|printer paper and toner' \
  'LL|2026-09-21|3900|OTH|framed print for the office wall' \
  'END|4' > expenses.ll
shown='"---\nname: ledgerline-import\ndescription: Convert expense notes\n---\n\n# Ledgerline Import\n"'
case "${1:-shell}" in
  # a shell read: what shows the load is the SKILL.md frontmatter in the command's output
  shell) action="{\"kind\": \"command\", \"command\": \"cd $(dirname "$skill") && sed -n 1,80p SKILL.md\", \"exit_code\": 0, \"ok\": true, \"output\": $shown}" ;;
  load) action='{"kind": "load", "name": "ledgerline-import", "ok": true}' ;;
  read) action="{\"kind\": \"read\", \"path\": \"~/.agents/skills/ledgerline-import/SKILL.md\", \"ok\": true, \"output\": $shown}" ;;
  *) echo "usage: good.sh shell|load|read" >&2; exit 2 ;;
esac
printf '{"finished": true, "covers": ["message", "command", "edit", "read", "load", "other"], "actions": [%s]}\n' "$action" > "$TRIAL_RECORD"
