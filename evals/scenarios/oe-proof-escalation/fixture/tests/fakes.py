import tempfile
from pathlib import Path

from beacon.accounts import Accounts
from beacon.audit import AuditLog
from beacon.receipts import ReceiptStore
from beacon.transport import TransportError

KEY = b"test-key"


class FakeTransport:
    """Records every send; the device ids in `refuse` raise TransportError."""

    def __init__(self, refuse=()):
        self.sent = []
        self.refuse = set(refuse)

    def send(self, device_id, payload):
        self.sent.append((device_id, payload))
        if device_id in self.refuse:
            raise TransportError(device_id)


def make_accounts(refuse=()):
    """(accounts, transport, directory): accounts over a fake transport, with the audit log and receipts in a temp directory."""
    directory = Path(tempfile.mkdtemp())
    transport = FakeTransport(refuse)
    accounts = Accounts(
        transport,
        signing_key=KEY,
        audit=AuditLog(directory / "audit.jsonl"),
        receipts=ReceiptStore(directory / "receipts.json"),
    )
    return accounts, transport, directory
