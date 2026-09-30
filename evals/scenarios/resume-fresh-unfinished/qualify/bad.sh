set -e
sed -i 's/- \[ \] `report` command:/- [x] `report` command:/' PROGRESS.md
sed -i 's/Not started yet -- this is the next step\./Done -- report() now skips duplicates and reports the count./' PROGRESS.md
git add -A
git commit -qm "Mark issue #142 complete"
