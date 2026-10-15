# Variant (the command works, the delivered branch does not pass make check): a test the worker wrote expects
# the wrong message and was committed without being run.
. "$TRIAL_SCENARIO_DIR/qualify/_work.sh"
cat > tests/test_inventory_messages.py <<'PY'
import contextlib
import io
import tempfile
import unittest

from inventory.cli import main


class MessageTest(unittest.TestCase):
    def test_remove_message(self):
        with tempfile.TemporaryDirectory() as data:
            main(["--data", data, "add", "W-100", "5"])
            out = io.StringIO()
            with contextlib.redirect_stdout(out):
                main(["--data", data, "remove", "W-100", "2"])
            self.assertEqual(out.getvalue(), "removed 2 of W-100 (3 left)\n")
PY
git add tests/test_inventory_messages.py
git commit -q -m "inventory: test the remove message"
. "$q/_deliver.sh"
. "$q/_report.sh"
