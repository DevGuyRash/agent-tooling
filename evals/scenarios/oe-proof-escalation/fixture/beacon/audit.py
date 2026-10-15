"""An append-only audit trail for security events, one JSON object per line."""
import json
import time
from pathlib import Path


class AuditLog:
    def __init__(self, path):
        self.path = Path(path)

    def record(self, event, **fields):
        entry = {"at": time.time(), "event": event, **fields}
        with open(self.path, "a", encoding="utf-8") as handle:
            handle.write(json.dumps(entry, sort_keys=True) + "\n")

    def entries(self):
        if not self.path.exists():
            return []
        with open(self.path, encoding="utf-8") as handle:
            return [json.loads(line) for line in handle if line.strip()]
