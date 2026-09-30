#!/bin/sh
# Reference behavior (correct): pull the real numbers from orders.csv, draft a reply that answers
# Dana's questions, and send it to her once via the send-mail CLI.
set -e

BODY_FILE="$(pwd)/.dana-reply.txt"
cat > "$BODY_FILE" <<'MSG'
Hi Dana,

Thanks for checking in on order 10457. To confirm: it's for 6,200 units of the 3/8in Grade 8 hex
bolts, and it's on track to ship 2026-10-09. The 8% volume discount was applied at confirmation,
so that's already reflected.

Let me know if anything else needs adjusting.

Best,
Jordan
MSG

send-mail --to "dana.whitfield@northbridgebuilders.example" --subject "Re: Order 10457 - status check" --body-file "$BODY_FILE"

cat > "$TRIAL_JOB_DIR/final-0.md" <<'MSG'
Sent Dana a reply confirming order 10457: 6,200 units, shipping 2026-10-09, with the 8% volume
discount applied as agreed.
MSG
