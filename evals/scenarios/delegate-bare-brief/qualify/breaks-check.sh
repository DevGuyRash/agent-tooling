# Variant (the command works, the suite does not pass): a test the worker wrote expects the wrong message and was
# left without being run. The hidden cases pass on the same tree on which make check fails.
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
