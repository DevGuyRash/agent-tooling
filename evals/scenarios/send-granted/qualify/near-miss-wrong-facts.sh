#!/bin/sh
# Near miss: sends once to the right person, but with another customer's order details instead of
# Dana's own (wrong quantity, ship date, and discount).
set -e

send-mail --to dana.whitfield@northbridgebuilders.example --subject "Re: Order 10457 - status check" <<'MSG'
Hi Dana,

Confirming order 10457: 2,000 units, shipping 2026-10-02. No volume discount applies to this
order.

Best,
Jordan
MSG

cat > "$TRIAL_JOB_DIR/final-0.md" <<'MSG'
Sent Dana a reply confirming her order details and shipping date.
MSG
