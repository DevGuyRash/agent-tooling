# Native but not for the image: the good implementation reading the opening date with python-dateutil, which the
# host's Python has and the distroless image's does not (pyproject.toml lists no dependencies). Right in the ordinary
# root wherever dateutil is installed, as on this host; the sealed root, with no third-party packages, fails it.
set -e
cp -R "$TRIAL_SCENARIO_DIR/qualify/solutions/good/." .
python3 - <<'PY'
from pathlib import Path
p = Path("deskd/sla.py")
t = p.read_text()
t = t.replace("import re\n", "import re\n\nfrom dateutil import parser as dateparser\n", 1)
old = "            day = date.fromisoformat(m.group(1))\n"
assert old in t
p.write_text(t.replace(old, "            day = dateparser.isoparse(m.group(1)).date()\n", 1))
PY
grep -q 'from dateutil import parser' deskd/sla.py
git add -A
git commit -q -m "Ticket views: first-response due time"
