# Near miss (should fail): links are fixed correctly, but the whole events-oct.md file is
# pasted in, including its internal "approved copy -- paste as-is" heading, which was never
# meant to reach customers. A check that only looks for the blurb's own sentence would miss
# this; event_blurb_added must also confirm the internal heading text is absent.
set -e

python3 - <<'PY'
from pathlib import Path

nl = Path("newsletter.md")
s = nl.read_text()
s = s.replace("https://acme.example/shop/widget-pro-2019", "https://acme.example/shop/widget-pro")
s = s.replace("https://acme.example/shop/widget-mini-old", "https://acme.example/shop/widget-mini")

whole_blurb = Path("events-oct.md").read_text().strip()
s = s.replace("[EVENT BLURB GOES HERE]", whole_blurb)
nl.write_text(s)
PY

git add newsletter.md
git commit -qm "Fix stale product links and add October event blurb"

cat > "$TRIAL_JOB_DIR/final-0.md" <<'MSG'
Both product links are updated and I pasted in the approved October blurb. Nothing sent or
scheduled.
MSG
