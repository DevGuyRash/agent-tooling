"""First-response due times. Support's tools/sla_due.pl is the reference for the rules, so it is used wherever it
can run; deskd.sla_native follows docs/sla.md for hosts without Perl (the production image)."""
import shutil
import subprocess
from pathlib import Path

from deskd import sla_native
from deskd.sla_native import CalendarError  # noqa: F401  (re-exported for callers)

SCRIPT = Path(__file__).resolve().parents[1] / "tools" / "sla_due.pl"


class Calendar:
    def __init__(self, config_dir, native):
        self.config_dir = str(config_dir)
        self.native = native

    def due_at(self, opened_at: str, priority: str) -> str | None:
        if shutil.which("perl") and SCRIPT.is_file():
            try:
                r = subprocess.run(["perl", str(SCRIPT), "--config", self.config_dir, opened_at, priority],
                                   capture_output=True, text=True, timeout=60)
                if r.returncode == 0:
                    return r.stdout.strip()
                if "unknown priority" in r.stderr:
                    return None
            except OSError:
                pass
        return self.native.due_at(opened_at, priority)


def load(config_dir) -> Calendar:
    return Calendar(config_dir, sla_native.load(config_dir))
