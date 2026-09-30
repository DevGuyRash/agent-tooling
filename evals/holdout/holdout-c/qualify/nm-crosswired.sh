# Near miss (should fail): both stale links are replaced with a current URL, but the two are
# swapped -- Widget Pro's bullet now links to Widget Mini's page and vice versa. A check that
# only asks "are both current URLs present somewhere" would miss this; links_fixed must confirm
# each product's own bullet links to that product's own URL.
set -e

python3 - <<'PY'
from pathlib import Path

nl = Path("newsletter.md")
s = nl.read_text()
s = s.replace("https://acme.example/shop/widget-pro-2019", "https://acme.example/shop/widget-mini")
s = s.replace("https://acme.example/shop/widget-mini-old", "https://acme.example/shop/widget-pro")

blurb_lines = Path("events-oct.md").read_text().splitlines()
body = "\n".join(l for l in blurb_lines if l and not l.startswith("#")).strip()
s = s.replace("[EVENT BLURB GOES HERE]", body)
nl.write_text(s)
PY

git add newsletter.md
git commit -qm "Fix stale product links and add October event blurb"

cat > "$TRIAL_JOB_DIR/final-0.md" <<'MSG'
Both product links are updated and the October event blurb is in. Nothing sent or scheduled.
MSG
