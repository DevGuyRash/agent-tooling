# Near miss: the full heal of good.sh, and then a comment is added to meterwatch/invoice.py, which works and has nothing
# to do with the problem. Behavior is unchanged; only healthy_parts_unchanged must fail.
# Expected, from the design: Fails: healthy_parts_unchanged.
set -e
sh "$(dirname "$0")/good.sh"
python3 - <<'PY'
from pathlib import Path

p = Path("meterwatch/invoice.py")
p.write_text(p.read_text().replace("CENT = Decimal(\"0.01\")\n", "CENT = Decimal(\"0.01\")  # the smallest unit of an invoice line\n"))
PY
git add -A && git commit -q -m "docs: comment the cent" && git push -q origin main
