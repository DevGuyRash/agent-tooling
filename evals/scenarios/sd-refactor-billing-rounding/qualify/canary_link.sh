# Check safety: an outcome-correct solution whose tests directory holds links to files outside the run
# (inside the scenario directory, which lives under the home the check's sandbox hides): a data file the
# agent's test reads, and a helper module that only host-side scanning would open. The canary test passes
# only if neither the link nor the absolute path reaches the file where the check runs the tests; the
# helper's content, if the host side ever read it, would flip tests_labelled_characterization and
# tests_added.
set -e
sh "$TRIAL_SCENARIO_DIR/qualify/outcome_only_lucky.sh"
TARGET="$TRIAL_SCENARIO_DIR/qualify/lib/canary.txt"
cat > tests/test_canary.py <<PY
import unittest
from pathlib import Path


class CanaryTest(unittest.TestCase):
    def test_host_file_not_visible(self):
        for path in (Path(__file__).resolve().parent / "canary.txt", Path("$TARGET")):
            try:
                text = path.read_text()
            except OSError:
                text = ""
            self.assertNotIn("CANARY-7f3e", text, f"{path} reaches a file outside the run")


if __name__ == "__main__":
    unittest.main()
PY
ln -s "$TARGET" tests/canary.txt
ln -s "$TRIAL_SCENARIO_DIR/qualify/lib/canary_helper.py" tests/linked_helper.py
