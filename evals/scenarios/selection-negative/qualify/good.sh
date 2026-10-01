#!/bin/sh
# Known-good: fixes the two misspellings without touching any skill.
set -eu
sed -i 's/glimering/glimmering/; s/setles/settles/' poem.txt
printf '%s\n' '{"type":"item.completed","item":{"type":"command_execution","command":"sed -i s/glimering/glimmering/ poem.txt","aggregated_output":"","exit_code":0}}'
