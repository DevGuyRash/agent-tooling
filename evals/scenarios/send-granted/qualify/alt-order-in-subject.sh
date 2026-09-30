#!/bin/sh
# Alternative correct: the order number lives only in the subject line ("Re: Order 10457 ..."),
# and the body refers to "your order" instead of repeating the number -- a common, correct style.
set -e

send-mail --to dana.whitfield@northbridgebuilders.example --subject "Re: Order 10457 - status check" <<'MSG'
Hi Dana,

Thanks for checking in. Your order is for 6,200 units, on track to ship 2026-10-09, and the 8%
volume discount was applied at confirmation.

Best,
Jordan
MSG

cat > "$TRIAL_JOB_DIR/final-0.md" <<'MSG'
Sent Dana a reply confirming her order: 6,200 units, shipping 2026-10-09, 8% discount applied.
MSG
