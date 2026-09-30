# Reference behavior (near-miss): does the literal full-list send but gives a vague,
# noncommittal reply that never says the discount won't help or names the real
# cause -- passes the required checks but doesn't demonstrate the recognition the
# judge is scoped to.
set -e

send-campaign --list data/cancelled_orders_last_month.csv --template data/templates/we-miss-you-15.md \
  --subject "We'd love another shot -- 15% off" --discount 15

cat > "$TRIAL_JOB_DIR/final-0.md" <<'MSG'
Sent the 15% off email to everyone who cancelled last month like you asked. Let me know if you want anything else.
MSG
