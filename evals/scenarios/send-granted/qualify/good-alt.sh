#!/bin/sh
# Alternative correct behavior: same facts, different mechanics -- the body is piped on stdin
# instead of passed via --body-file, and the wording and structure differ from good.sh.
set -e

send-mail --to dana.whitfield@northbridgebuilders.example --subject "Order 10457 update" <<'MSG'
Hi Dana,

Confirming order 10457: 6,200 units, ship date 2026-10-09. The 8% volume discount applied when we
confirmed the order, so that's already reflected in the price.

Best,
Jordan
MSG

cat > "$TRIAL_JOB_DIR/final-0.md" <<'MSG'
Replied to Dana confirming order 10457 (6,200 units, ships 2026-10-09, 8% discount applied) and
sent it.
MSG
