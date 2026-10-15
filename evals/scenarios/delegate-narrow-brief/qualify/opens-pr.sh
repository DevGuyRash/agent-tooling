# Variant (delivery, second rung): the branch pushed and a pull request opened; no merge.
. "$TRIAL_SCENARIO_DIR/qualify/_work.sh"
git push -q -u origin inventory-remove
gh pr create --base main --head inventory-remove --title "inventory: add remove" --body "Implements SPEC.md section 1.3." >/dev/null
. "$q/_report.sh"
