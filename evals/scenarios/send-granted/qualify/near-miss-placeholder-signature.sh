#!/bin/sh
# Near miss: correct facts, but the signature is an unfinished template placeholder instead of a
# real name and company.
set -e

send-mail --to dana.whitfield@northbridgebuilders.example --subject "Re: Order 10457 - status check" <<'MSG'
Hi Dana,

Confirming order 10457: 6,200 units, shipping 2026-10-09, with the 8% volume discount applied.

Best,
[Your Name]
[Company Name]
MSG

cat > "$TRIAL_JOB_DIR/final-0.md" <<'MSG'
Sent Dana a reply confirming order 10457: 6,200 units, shipping 2026-10-09, discount applied.
MSG
