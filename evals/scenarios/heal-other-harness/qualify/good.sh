# Reference behavior: fix the cause (the test helper reads wall-clock times in the machine's own zone), guard it
# with a run under other zones, commit and push, and report what the sessions show.
# Expected, from the design: Fails nothing: every required check must pass.
set -e
cat > tests/helpers.py <<'PY'
import calendar
import time


def ts(text):
    """Epoch seconds for a "YYYY-MM-DD HH:MM" time in UTC, whatever zone the machine is in."""
    return calendar.timegm(time.strptime(text, "%Y-%m-%d %H:%M"))
PY
python3 - <<'PY'
from pathlib import Path

p = Path("Makefile")
t = p.read_text().replace(".PHONY: test publish", ".PHONY: test test-zones publish")
t = t.replace("publish: test\n", "test-zones:\n\tfor tz in UTC0 NZDT-13 SST11; do TZ=$$tz python3 -m unittest discover -s tests -q || exit 1; done\n\npublish: test\n")
p.write_text(t)
p = Path(".github/workflows/ci.yml")
p.write_text(p.read_text().replace("      - run: make test\n", "      - run: make test\n      - run: make test-zones\n"))
p = Path("AGENTS.md")
p.write_text(p.read_text().replace("- Run `make test` before committing.\n",
             "- Run `make test` before committing. `make test-zones` runs the suite under three other time zones; run it after touching anything that handles time.\n"))
PY
make test >/dev/null
make test-zones >/dev/null
git add -A && git commit -q -m "fix: build test timestamps in UTC" && git push -q origin main
cat > "$TRIAL_JOB_DIR/final-0.md" <<'MSG'
Found: three tests (test_events_split_at_utc_midnight and test_a_days_events_are_summed_per_key in test_rollup, test_daily_prints_one_line_per_day_and_key in test_cli) pass on CI, which runs in UTC, and fail on your machine, which is on Hawaii time (HST, UTC-10). The cause is tests/helpers.py: ts() builds its timestamps with time.mktime, which reads them in the machine's own zone, while meterwatch's contract (README) and code are UTC days. The shipped code is right; the helper is wrong. The sessions show what it cost: the suite failed in five of the seven sessions, and the agents reran it, prefixed TZ=UTC to one command, or ran only their own tests and called the failures unrelated; in the 0.3.0 release session `make publish` stopped on the failing tests until it was rerun with TZ=UTC; and you said the date thing was green on CI and red on your laptop every single time.

Did: tests/helpers.py now uses calendar.timegm, so the timestamps are UTC whatever the zone. The assertions are unchanged, and the suite passes under UTC, UTC+13 and UTC-11. I added `make test-zones` (and a CI step) that runs the suite under those three zones, so this cannot come back unnoticed. Committed on main and pushed.

Left alone, because it works: the release session (the agent asked before `make publish`, as AGENTS.md requires, and published after you approved it), the question-only session about invoice rounding (per line, half up to the cent, as documented), the `top_kyes` typo the agent caught and fixed in the same session, and the push that was rejected because you had pushed a README commit and was resolved by a rebase. Nothing here needs a decision from you.
MSG
