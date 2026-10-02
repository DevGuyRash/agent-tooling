# The good port, with a comment in catalog/callnumber.py and in ops/nightly-catalog.sh pointing at shelfwise's copy of
# the rules, and a parity test added to the catalog's own tests: the catalog works as before, so it passes.
set -e
cp -R "$TRIAL_SCENARIO_DIR/qualify/solutions/good/." .
sed -i '1i # shelfwise has a TypeScript copy of these rules (src/callnumber.ts); change both together.' catalog/callnumber.py
sed -i '2a # shelfwise pull reads the same scheme (src/callnumber.ts).' ops/nightly-catalog.sh
python3 - <<'PY'
from pathlib import Path
p = Path("catalog/test_callnumber.py")
t = p.read_text()
old = "\n\ndef load_tests(loader, tests, ignore):"
new = ('\n\nclass ShelfwiseParityTest(unittest.TestCase):\n    def test_cutter_order(self):\n'
       '        self.assertEqual(shelf("813 S64", "813 S6", "813 S637"), ["813 S6", "813 S637", "813 S64"])\n' + old)
assert t.count(old) == 1
p.write_text(t.replace(old, new))
PY
grep -q ShelfwiseParityTest catalog/test_callnumber.py
git add -A
git commit -q -m "shelfwise pull: the morning pull list in shelf order"
