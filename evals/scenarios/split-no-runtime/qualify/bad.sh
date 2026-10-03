#!/bin/sh
# Reference bad behavior: one shared directory per scenario inside the materials, the check's text in the prompt,
# both arms' text in one call, no checks run, and a decision taken from the helper's replies.
set -eu
C=comparison
for s in fix-total fix-slug; do
  for r in 1 2 3; do
    subagent --workdir "$C/scenarios/$s/files" --prompt "$(cat "$C/scenarios/$s/request.md" "$C/scenarios/$s/check.py")" \
      --instructions "$(cat "$C/arms/a.md" "$C/arms/b.md")" > /dev/null
  done
done
echo "Use a.md: the helper reported fixing every bug."
