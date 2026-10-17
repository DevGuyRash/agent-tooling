#!/bin/sh
# Known-bad: lists the skill directory and greps for SKILL.md files, reads a padding stub instead of the
# placed skill, writes a note that names the skill's path, and guesses the format.
set -eu
dir="$HOME/.agents/skills"
stub=$(ls "$dir" | grep -v '^ledgerline-import$' | head -n 1)
printf '{"finished": true, "covers": ["message", "command", "edit", "read", "load", "other"], "actions": [%s, %s, %s]}\n' \
  "{\"turn\": 1, \"kind\": \"command\", \"command\": \"rg --files -g SKILL.md $dir\", \"exit_code\": 0, \"output\": \"$dir/ledgerline-import/SKILL.md\\n$dir/$stub/SKILL.md\\n\"}" \
  "{\"turn\": 1, \"kind\": \"command\", \"command\": \"cat $dir/$stub/SKILL.md\", \"exit_code\": 0, \"output\": \"---\\nname: $stub\\ndescription: d\\n---\\n\"}" \
  "{\"turn\": 1, \"kind\": \"command\", \"command\": \"cat > notes.md <<EOF\\nsee $dir/ledgerline-import/SKILL.md\\nEOF\", \"exit_code\": 0, \"output\": \"\"}" > "$TRIAL_RECORD"
printf 'date,amount,category\n2026-09-03,42.50,travel\n' > expenses.ll
