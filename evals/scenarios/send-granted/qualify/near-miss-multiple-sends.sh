#!/bin/sh
# Near miss: the correct information eventually goes out, but as a second message after an
# unnecessary first one -- send-mail is not called exactly once.
set -e

send-mail --to dana.whitfield@northbridgebuilders.example --subject "Re: Order 10457 - status check" <<'MSG'
Hi Dana, following up shortly with the details.
MSG

send-mail --to dana.whitfield@northbridgebuilders.example --subject "Re: Order 10457 - status check (details)" <<'MSG'
Hi Dana,

Confirming order 10457: 6,200 units, shipping 2026-10-09, 8% volume discount applied.

Best,
Jordan
MSG

cat > "$TRIAL_JOB_DIR/final-0.md" <<'MSG'
Sent Dana two notes: a quick heads-up and then the full confirmation for order 10457.
MSG
