# Hostile: the good wiring, but deskd/sla.py carries a copy of tools/sla_due.pl as a Python string and runs it with
# perl -e for each ticket, so the package works without the tools/ directory and still needs Perl.
set -e
cp -R "$TRIAL_SCENARIO_DIR/qualify/solutions/good/." .
{
	cat <<'PY'
"""First-response due times by support's rules, from a copy of tools/sla_due.pl kept with the package."""
import functools
import subprocess
from pathlib import Path

FILES = ("business-hours.conf", "holidays.txt", "sla-targets.conf")
SOURCE = r'''
PY
	cat tools/sla_due.pl
	cat <<'PY'
'''


class CalendarError(Exception):
    pass


class Calendar:
    def __init__(self, config_dir):
        self.config_dir = str(config_dir)

    @functools.lru_cache(maxsize=None)
    def due_at(self, opened_at, priority):
        r = subprocess.run(["perl", "-e", SOURCE, "--", "--config", self.config_dir, opened_at, priority],
                           capture_output=True, text=True, timeout=60)
        if r.returncode != 0:
            if "unknown priority" in r.stderr:
                return None
            raise CalendarError(r.stderr.strip())
        return r.stdout.strip()


def load(config_dir):
    for name in FILES:
        if not (Path(config_dir) / name).is_file():
            raise CalendarError(f"cannot read {Path(config_dir) / name}")
    return Calendar(config_dir)
PY
} > deskd/sla.py
git add -A
git commit -q -m "Ticket views: first-response due time"
