"""First-response due times, as support's tools/sla_due.pl works them out (it stays the one source of the rules)."""
import functools
import subprocess
from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[1] / "tools" / "sla_due.pl"
FILES = ("business-hours.conf", "holidays.txt", "sla-targets.conf")


class CalendarError(Exception):
    pass


class Calendar:
    def __init__(self, config_dir):
        self.config_dir = str(config_dir)

    @functools.lru_cache(maxsize=None)
    def due_at(self, opened_at: str, priority: str) -> str | None:
        r = subprocess.run(["perl", str(SCRIPT), "--config", self.config_dir, opened_at, priority],
                           capture_output=True, text=True, timeout=60)
        if r.returncode != 0:
            if "unknown priority" in r.stderr:
                return None
            raise CalendarError(r.stderr.strip().removeprefix("sla_due: "))
        return r.stdout.strip()


def load(config_dir) -> Calendar:
    for name in FILES:
        path = Path(config_dir) / name
        if not path.is_file():
            raise CalendarError(f"cannot read {path}")
    return Calendar(config_dir)
