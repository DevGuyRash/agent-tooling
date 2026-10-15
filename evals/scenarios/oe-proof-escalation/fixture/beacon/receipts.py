"""Which critical notices each device has acknowledged, kept in a JSON file."""
import json
from pathlib import Path


class ReceiptStore:
    def __init__(self, path):
        self.path = Path(path)
        self._receipts = json.loads(self.path.read_text(encoding="utf-8")) if self.path.exists() else {}

    def expect(self, notice_id, device_id):
        self._receipts.setdefault(notice_id, {})[device_id] = False
        self._save()

    def acknowledge(self, notice_id, device_id):
        self._receipts[notice_id][device_id] = True
        self._save()

    def outstanding(self):
        return sorted((n, d) for n, devices in self._receipts.items() for d, seen in devices.items() if not seen)

    def _save(self):
        self.path.write_text(json.dumps(self._receipts, sort_keys=True), encoding="utf-8")
