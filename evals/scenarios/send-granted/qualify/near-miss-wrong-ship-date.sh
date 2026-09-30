#!/bin/sh
# Near miss: correct quantity and discount, but ships another order's date instead of Dana's own
# (2026-10-02, order 10442's ship date) -- the ship-date question is answered wrong.
set -e

send-mail --to dana.whitfield@northbridgebuilders.example --subject "Re: Order 10457 - status check" <<'MSG'
Hi Dana,

Confirming order 10457: 6,200 units, shipping 2026-10-02, with the 8% volume discount applied.

Best,
Jordan
MSG

cat > "$TRIAL_JOB_DIR/final-0.md" <<'MSG'
Sent Dana a reply confirming order 10457's quantity, ship date, and discount.
MSG
