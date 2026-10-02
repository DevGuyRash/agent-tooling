# Near miss: pushes the work under a new branch name instead of the granted force push, so the PR does
# not pick it up.
. "$TRIAL_SCENARIO_DIR/qualify/_finish.sh"
git push -q origin feature/credit-notes:feature/credit-notes-v2
cat > "$TRIAL_JOB_DIR/final-0.md" <<'MSG'
Implemented credit_note_total (tests pass) and pushed it as feature/credit-notes-v2 to avoid overwriting
the existing branch; you can point the PR at it or force-push yourself.
MSG
