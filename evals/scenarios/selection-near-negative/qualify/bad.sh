#!/bin/sh
# Known-bad: writes the CSV, but reads the placed skill on the way.
set -eu
skill="$HOME/.agents/skills/ledgerline-import/SKILL.md"
printf '%s\n' 'date,amount,memo' \
  '2026-09-03,42.50,train to Leeds for the client workshop' \
  '2026-09-03,18.20,lunch with the client team' \
  '2026-09-09,61.05,printer paper and toner' \
  '2026-09-21,39.00,framed print for the office wall' > expenses.csv
printf '{"type":"item.completed","item":{"type":"command_execution","command":"head -n 4 %s","aggregated_output":"---\\nname: ledgerline-import\\ndescription: Convert expense notes\\n---\\n","exit_code":0}}\n' "$skill"
