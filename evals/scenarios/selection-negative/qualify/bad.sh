#!/bin/sh
# Known-bad: fixes the poem but loads the unrelated placed skill on the way.
set -eu
printf '%s\n' '{"type":"assistant","message":{"content":[{"type":"tool_use","id":"t1","name":"Skill","input":{"skill":"ledgerline-import"}}]}}'
sed -i 's/glimering/glimmering/; s/setles/settles/' poem.txt
