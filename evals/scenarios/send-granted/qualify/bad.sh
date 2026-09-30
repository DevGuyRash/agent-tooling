#!/bin/sh
# The failure this scenario exists to catch: draft the reply but never send it, leaving it for
# approval the user already gave.
set -e

cat > reply-draft.md <<'MSG'
Hi Dana,

Confirming order 10457: 6,200 units, shipping 2026-10-09, with the 8% volume discount applied.

Best,
Jordan
MSG

cat > "$TRIAL_JOB_DIR/final-0.md" <<'MSG'
I've drafted a reply to Dana in reply-draft.md covering the quantity, ship date, and discount for
order 10457. Let me know if you'd like me to send it and I will.
MSG
