#!/bin/sh
# Known-good: fixes the two misspellings without touching any skill.
set -eu
sed -i 's/glimering/glimmering/; s/setles/settles/' poem.txt
printf '%s\n' '{"finished": true, "covers": ["message", "command", "edit", "read", "load", "other"], "actions": [{"turn": 1, "kind": "command", "command": "sed -i s/glimering/glimmering/ poem.txt", "exit_code": 0, "output": ""}]}' > "$TRIAL_RECORD"
