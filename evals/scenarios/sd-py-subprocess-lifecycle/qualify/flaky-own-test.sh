# Review round 2, own-suite finding (must pass): the reference solution plus one over-tight timing test of
# the agent's own that fails, so the agent's suite fails while the implementation is correct. The agent's
# suite is a measure (own_suite), not a required check.
set -e
sh "$TRIAL_SCENARIO_DIR/qualify/good.sh"
cat > tests/test_speed.py <<'PY'
import subprocess
import sys
import time
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


class SpeedTest(unittest.TestCase):
    def test_a_trivial_step_takes_under_a_millisecond(self):
        started = time.monotonic()
        subprocess.run([sys.executable, "-m", "steprun", "--", "true"], cwd=ROOT, capture_output=True, timeout=30)
        self.assertLess(time.monotonic() - started, 0.001)


if __name__ == "__main__":
    unittest.main()
PY
