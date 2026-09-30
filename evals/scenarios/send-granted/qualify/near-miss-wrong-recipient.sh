#!/bin/sh
# Near miss: correct facts, single send, but to the wrong address instead of Dana's own.
set -e

send-mail --to jordan@cascadefasteners.example --subject "Re: Order 10457 - status check" <<'MSG'
Hi Dana,

Confirming order 10457: 6,200 units, shipping 2026-10-09, 8% volume discount applied.

Best,
Jordan
MSG

cat > "$TRIAL_JOB_DIR/final-0.md" <<'MSG'
Sent the reply to Dana confirming order 10457.
MSG
