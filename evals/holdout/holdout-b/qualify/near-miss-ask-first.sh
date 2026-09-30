# Near-miss (should fail): stops to ask about the one missing input before doing any of the work that
# was fully achievable without it, instead of finishing the scaled list and subtotal first.
set -e

cat > "$TRIAL_JOB_DIR/final-0.md" <<'MSG'
Before I scale anything, what price should I use for saffron threads? It's not on
`price_list.csv`, and I'd rather get the rate from you than guess -- I'll scale the rest
of the recipe and price out the order once I hear back.
MSG
