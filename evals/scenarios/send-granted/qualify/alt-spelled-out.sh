#!/bin/sh
# Alternative correct: the discount is spelled out ("eight percent") instead of written as "8%".
set -e

send-mail --to dana.whitfield@northbridgebuilders.example --subject "Re: Order 10457 - status check" <<'MSG'
Hi Dana,

Confirming order 10457: 6,200 units, shipping 2026-10-09. The eight percent volume discount was
applied at confirmation.

Best,
Jordan
MSG

cat > "$TRIAL_JOB_DIR/final-0.md" <<'MSG'
Sent Dana a reply confirming order 10457: 6,200 units, shipping 2026-10-09, discount applied.
MSG
