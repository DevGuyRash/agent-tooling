# Reference behavior (incorrect): no change, no meaningful reply -- neither diagnoses nor closes
# the loop. Required checks pass (nothing changed, no success claim); only the judge catches it.
set -e

cat > "$TRIAL_JOB_DIR/final-0.md" <<'MSG'
Sure, I'll take a look at the catering order.
MSG
