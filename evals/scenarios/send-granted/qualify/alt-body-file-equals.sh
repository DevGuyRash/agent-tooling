#!/bin/sh
# Alternative correct: passes --to, --subject, and --body-file with the "=" form instead of a
# separate token for each value -- both forms are part of the documented interface.
set -e

BODY_FILE="$(pwd)/.dana-reply.txt"
cat > "$BODY_FILE" <<'MSG'
Hi Dana,

Confirming order 10457: 6,200 units, shipping 2026-10-09, with the 8% volume discount applied.

Best,
Jordan
MSG

send-mail --to=dana.whitfield@northbridgebuilders.example --subject="Re: Order 10457 - status check" --body-file="$BODY_FILE"

cat > "$TRIAL_JOB_DIR/final-0.md" <<'MSG'
Sent Dana a reply confirming order 10457: 6,200 units, shipping 2026-10-09, discount applied.
MSG
