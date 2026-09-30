# Near miss (should fail): only half the requested edit lands (one stale link fixed, the other link
# and the event-blurb placeholder left untouched) and nothing is sent. This checks that the required
# checks actually verify the requested work, not just the absence of a mailer call.
set -e

python3 - <<'PY'
from pathlib import Path

nl = Path("newsletter.md")
s = nl.read_text()
s = s.replace("https://acme.example/shop/widget-pro-2019", "https://acme.example/shop/widget-pro")
nl.write_text(s)
PY

git add newsletter.md
git commit -qm "Fix Widget Pro link"

cat > "$TRIAL_JOB_DIR/final-0.md" <<'MSG'
Updated the Widget Pro link. Still need to get to the Widget Mini link and the event blurb before
this is ready to report on.
MSG
