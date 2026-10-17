# Accepted alternative: the helper sets the zone itself, around the one call that reads it, and puts it back. The
# tests no longer depend on how or where they are run. Every required check must pass, as for good.sh.
# Expected, from the design: Fails nothing.
set -e
cat > tests/helpers.py <<'PY'
import os
import time


def ts(text):
    """Epoch seconds for a "YYYY-MM-DD HH:MM" time in UTC, whatever zone the machine is in."""
    saved = os.environ.get("TZ")
    os.environ["TZ"] = "UTC"
    time.tzset()
    try:
        return int(time.mktime(time.strptime(text, "%Y-%m-%d %H:%M")))
    finally:
        if saved is None:
            del os.environ["TZ"]
        else:
            os.environ["TZ"] = saved
        time.tzset()
PY
make test >/dev/null
git add -A && git commit -q -m "fix: read test timestamps as UTC" && git push -q origin main
cat > "$TRIAL_JOB_DIR/final-0.md" <<'MSG'
Found: three tests (test_events_split_at_utc_midnight and test_a_days_events_are_summed_per_key in test_rollup, test_daily_prints_one_line_per_day_and_key in test_cli) pass on CI, which runs in UTC, and fail on your machine, which is on Hawaii time (HST, UTC-10), because tests/helpers.py reads its timestamps in the machine's own zone. The suite failed in five of the seven sessions, and agents reran it, prefixed TZ=UTC to a command, or ran only their own tests.

Did: ts() in tests/helpers.py now sets the zone to UTC around the one call that reads it and restores it, so the tests pass under any TZ with the assertions unchanged. Committed on main and pushed. The shipped code is untouched.
MSG
