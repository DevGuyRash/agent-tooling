# Reference behavior: no repository changes, but a reply that never confirms the chapter's status
# either way, so it should still fail the judge question.
cat > "$TRIAL_JOB_DIR/final-0.md" <<'MSG'
Sure thing — let me know if there's anything else you'd like me to look at.
MSG
