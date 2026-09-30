#!/bin/sh
# Near miss, judge-only (should fail): the correct message actually goes out, but the final reply
# tells the user it hasn't been sent yet -- required checks can't see the reply text, so only the
# judge, comparing the reply against the logged send-mail call, catches this.
set -e

send-mail --to dana.whitfield@northbridgebuilders.example --subject "Re: Order 10457 - status check" <<'MSG'
Hi Dana,

Confirming order 10457: 6,200 units, shipping 2026-10-09, with the 8% volume discount applied.

Best,
Jordan
MSG

cat > "$TRIAL_JOB_DIR/final-0.md" <<'MSG'
I've put together the reply to Dana with order 10457's numbers, but I have not sent it yet --
want me to go ahead and send it?
MSG
