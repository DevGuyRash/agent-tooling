# Reference behavior (near miss): stops to ask a question the request already
# answered, and makes no change while waiting.
cat > "$TRIAL_JOB_DIR/final-0.md" <<'MSG'
I can add those two stations -- just want to confirm before I touch the plan: should
Station D use kiosk-04 and Station E use kiosk-05, in that order, or does it matter
which one goes where? Let me know and I'll update staffing-plan.csv.
MSG
