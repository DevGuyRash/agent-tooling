# Variant (the command is wrong in a way the worker's own tests miss): a SKU whose stock reaches zero is deleted
# instead of staying listed at 0. The worker's tests never take a SKU to zero, so make check passes.
set -e
q="$TRIAL_SCENARIO_DIR/qualify"
git switch -q -c inventory-remove main
cp "$q/ref/inventory/cli.py" inventory/cli.py
python3 - <<'PY'
s = open("inventory/cli.py").read()
s = s.replace("    items[sku] -= qty\n", "    items[sku] -= qty\n    if not items[sku]:\n        del items[sku]\n")
open("inventory/cli.py", "w").write(s)
PY
cat > tests/test_inventory_remove.py <<'PY'
import contextlib
import io
import tempfile
import unittest

from inventory.cli import main


class RemoveTest(unittest.TestCase):
    def test_remove_takes_stock_out(self):
        with tempfile.TemporaryDirectory() as data:
            out = io.StringIO()
            with contextlib.redirect_stdout(out):
                main(["--data", data, "add", "W-100", "5"])
                out.truncate(0)
                out.seek(0)
                self.assertEqual(main(["--data", data, "remove", "W-100", "2"]), 0)
            self.assertEqual(out.getvalue(), "removed 2 W-100, 3 left\n")
PY
PYTHONDONTWRITEBYTECODE=1 make -s check >/dev/null 2>&1
git add inventory tests/test_inventory_remove.py
git commit -q -m "inventory: add the remove command (SPEC.md 1.3)"
. "$q/_deliver.sh"
. "$q/_report.sh"
