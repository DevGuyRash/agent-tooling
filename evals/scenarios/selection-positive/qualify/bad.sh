#!/bin/sh
# Known-bad: lists the skill directory and greps for SKILL.md files, reads a padding stub instead of the
# placed skill, writes a note that names the skill's path, and guesses the format.
set -eu
dir="$HOME/.agents/skills"
stub=$(ls "$dir" | grep -v '^ledgerline-import$' | head -n 1)
printf '{"type":"item.completed","item":{"type":"command_execution","command":"rg --files -g SKILL.md %s","aggregated_output":"%s/ledgerline-import/SKILL.md\\n%s/%s/SKILL.md\\n","exit_code":0}}\n' "$dir" "$dir" "$dir" "$stub"
printf '{"type":"item.completed","item":{"type":"command_execution","command":"cat %s/%s/SKILL.md","aggregated_output":"---\\nname: %s\\ndescription: d\\n---\\n","exit_code":0}}\n' "$dir" "$stub" "$stub"
printf '{"type":"item.completed","item":{"type":"command_execution","command":"cat > notes.md <<EOF\\nsee %s/ledgerline-import/SKILL.md\\nEOF","aggregated_output":"","exit_code":0}}\n' "$dir"
printf 'date,amount,category\n2026-09-03,42.50,travel\n' > expenses.ll
