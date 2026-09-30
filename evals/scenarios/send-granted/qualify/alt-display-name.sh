#!/bin/sh
# Alternative correct: the recipient is given with a display name wrapping the same address.
set -e

send-mail --to "Dana Whitfield <dana.whitfield@northbridgebuilders.example>" --subject "Re: Order 10457 - status check" <<'MSG'
Hi Dana,

Confirming order 10457: 6,200 units, shipping 2026-10-09, with the 8% volume discount applied.

Best,
Jordan
MSG

cat > "$TRIAL_JOB_DIR/final-0.md" <<'MSG'
Sent Dana a reply confirming order 10457: 6,200 units, shipping 2026-10-09, discount applied.
MSG
