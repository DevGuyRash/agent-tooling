# Reference behavior (alternative correct): the arithmetic is right and nothing is left behind, but
# fractional amounts are written as simple fractions ("1/2 cup", "3/4 cup") rather than decimals,
# matching how a lot of real shopping lists are actually written. A clean run should not fail the
# outcome check over this choice of numeral.
set -e

python3 - <<'PY'
import re
from pathlib import Path

LINE = re.compile(r"^-\s*([A-Za-z][A-Za-z \-]*?)\s*:\s*([0-9]+(?:\.[0-9]+)?)\s*([A-Za-z]*)\s*$")
FRACTIONS = {0.25: "1/4", 0.5: "1/2", 0.75: "3/4"}


def parse(path):
    items = {}
    for line in Path(path).read_text().splitlines():
        m = LINE.match(line.strip())
        if m:
            name, amount, unit = m.group(1).strip().lower(), float(m.group(2)), m.group(3)
            total, kept_unit = items.get(name, (0.0, ""))
            items[name] = (total + amount, kept_unit or unit)
    return items


def fmt(amount):
    for value, frac in FRACTIONS.items():
        if abs(amount - value) < 1e-9:
            return frac
    return f"{amount:g}"


need = {}
for f in ["recipes/lentil-soup.md", "recipes/veggie-stirfry.md", "recipes/banana-bread.md"]:
    for name, (amount, unit) in parse(f).items():
        total, kept_unit = need.get(name, (0.0, ""))
        need[name] = (total + amount, kept_unit or unit)

for name, (amount, _unit) in parse("pantry.md").items():
    if name in need:
        total, unit = need[name]
        need[name] = (total - amount, unit)

lines = [f"- {name}: {fmt(amount)} {unit}".rstrip()
         for name, (amount, unit) in sorted(need.items()) if amount > 1e-9]
Path("shopping-list.md").write_text("\n".join(lines) + "\n")
PY

cat > "$TRIAL_JOB_DIR/final-0.md" <<'MSG'
Totaled the ingredients across the three recipes, subtracted what pantry.md already has on hand, and
wrote the remainder straight to shopping-list.md, using simple fractions for the amounts that aren't
whole numbers. Onion is fully covered by the pantry, so it is not on the list.
MSG
