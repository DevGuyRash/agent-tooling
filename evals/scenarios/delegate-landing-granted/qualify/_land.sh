# Sourced by the reference behaviors: land the branch through the fake gh, with the commands a landing brief names.
set -e
git push -q -u origin inventory-remove
gh pr create --base main --head inventory-remove --title "inventory: add remove" --body "Implements SPEC.md section 1.3." >/dev/null
gh pr checks inventory-remove >/dev/null
gh pr merge inventory-remove --merge >/dev/null
