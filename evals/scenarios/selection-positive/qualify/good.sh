#!/bin/sh
# Known-good: loads the placed skill, then writes the import file. $1 (codex, claude, or gemini) picks whose
# record format the load is written in, the way that host's executor would record it.
set -eu
skill="$HOME/.agents/skills/ledgerline-import/SKILL.md"
test -f "$skill"
printf '%s\n' 'LLv3' \
  'LL|2026-09-03|4250|TRV|train to Leeds for the client workshop' \
  'LL|2026-09-03|1820|MEA|lunch with the client team' \
  'LL|2026-09-09|6105|SUP|printer paper and toner' \
  'LL|2026-09-21|3900|OTH|framed print for the office wall' \
  'END|4' > expenses.ll
case "${1:-codex}" in
  # A shell read: what shows the load is the SKILL.md frontmatter in the command's output.
  codex) printf '{"type":"item.completed","item":{"type":"command_execution","command":"/bin/sh -lc \\"cd %s && sed -n 1,80p SKILL.md\\"","aggregated_output":"---\\nname: ledgerline-import\\ndescription: Convert expense notes\\n---\\n\\n# Ledgerline Import\\n","exit_code":0}}\n' "$(dirname "$skill")" ;;
  claude) printf '%s\n' '{"type":"assistant","message":{"content":[{"type":"tool_use","id":"t1","name":"Skill","input":{"skill":"ledgerline-import"}}]}}' ;;
  gemini) printf '%s\n' '{"type":"tool_use","tool_name":"activate_skill","tool_id":"t1","parameters":{"name":"ledgerline-import"}}' ;;
  *) echo "usage: good.sh codex|claude|gemini" >&2; exit 2 ;;
esac
