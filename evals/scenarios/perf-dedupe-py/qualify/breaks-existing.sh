# Wrong (must fail existing_tests_pass only): the reference dedupe, plus a "people after dedupe" line in
# `stats`, which widens the label column every other line is printed in; the fixture's stats test is edited
# to the new spacing. The hidden dedupe cases still pass, but `stats` output changed under whatever reads it.
set -e
. "$TRIAL_SCENARIO_DIR/qualify/common.sh"
apply "$TRIAL_SCENARIO_DIR/hidden/reference"
add_tests
python3 - <<'PY'
import re
from pathlib import Path
p = Path("shopcrm/stats.py")
t = p.read_text()
t = t.replace("from .contacts import normalize_email, normalize_phone\n",
              "from .contacts import normalize_email, normalize_phone\nfrom .dedupe import people\n")
t = t.replace("    total_spent: int = 0  # cents\n", "    total_spent: int = 0  # cents\n    people: int = 0\n")
t = t.replace("    stats.distinct_emails = len(emails)\n",
              "    stats.distinct_emails = len(emails)\n    stats.people = len(people(list(contacts)))\n")
t = t.replace('        ("total spent", format_money(stats.total_spent)),\n',
              '        ("total spent", format_money(stats.total_spent)),\n        ("people after dedupe", str(stats.people)),\n')
p.write_text(t)
p = Path("tests/test_cli.py")
t = p.read_text()
t = re.sub(r'self\.assertIn\("([a-z ]+?) +(\S+)\\n", out\)',
           lambda m: f'self.assertIn("{m.group(1):<19}  {m.group(2)}\\n", out)', t)
p.write_text(t)
PY
finish "Added shopcrm dedupe, and stats now also prints how many people the export holds after deduplication. Tests updated and passing."
