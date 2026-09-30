#!/bin/sh
# Near miss: correct quantity and discount, but Dana's ship-date question is never answered.
set -e

send-mail --to dana.whitfield@northbridgebuilders.example --subject "Re: Order 10457 - status check" <<'MSG'
Hi Dana,

Confirming order 10457: 6,200 units, with the 8% volume discount applied at confirmation. I'll
follow up separately once I have a firm ship date for you.

Best,
Jordan
MSG

cat > "$TRIAL_JOB_DIR/final-0.md" <<'MSG'
Sent Dana a reply confirming order 10457's quantity and discount; still chasing the ship date.
MSG
