# Reference behavior (a required finding implemented the reviewer's way, not the spec's): the retry as a decorator
# with three attempts, exponential backoff, and jitter, instead of R9's four attempts after 1, 2, and 4 seconds
# through a sleep argument. The rest as good.
. "$TRIAL_SCENARIO_DIR/qualify/_lib.sh"
edit fix carryover floor reject formats cache replay
edit alt retry-decorator
add_tests test_real.py test_formats.py test_cache.py test_replay.py
cat > tests/test_retry_decorator.py <<'PY'
import time
import unittest
from unittest import mock

from stampcard.directory import Card
from stampcard.notify import notify_reward


class RetryDecoratorTest(unittest.TestCase):
    def test_a_failing_transport_is_tried_three_times(self):
        calls = []

        def down(message):
            calls.append(message)
            raise OSError("gateway down")

        with mock.patch.object(time, "sleep"):
            self.assertFalse(notify_reward(Card("C-001", "Ada", 0), down))
        self.assertEqual(len(calls), 3)
PY
edit dispose line 1=fixed,2=fixed,3=fixed,4=fixed,5=fixed,6=fixed,7=fixed
run_check
