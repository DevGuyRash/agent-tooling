#!/bin/sh
# Near miss, judge-only (should fail): quantity and ship date are both correct, and the required
# checks can't tell that the reply gets the discount question backwards -- it tells Dana the 8%
# volume discount did NOT make it onto her order, when orders.csv shows it was applied. Only the
# judge, comparing the reply against the orders.csv row, can catch this.
set -e

send-mail --to dana.whitfield@northbridgebuilders.example --subject "Re: Order 10457 - status check" <<'MSG'
Hi Dana,

Confirming order 10457: 6,200 units, shipping 2026-10-09. Unfortunately the 8% volume discount we
talked about did not make it onto this order, so it's billing at full price.

Best,
Jordan
MSG

cat > "$TRIAL_JOB_DIR/final-0.md" <<'MSG'
Sent Dana a reply on order 10457 with the quantity, ship date, and discount status.
MSG
