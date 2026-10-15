"""Sending notices to a user's devices."""
import itertools

from . import signing
from .transport import TransportError

_ids = itertools.count(1)


def send_critical(accounts, user, kind):
    """An account-security notice (docs/notices.md): signed, audited, and tracked until each device acknowledges it."""
    notice_id = f"n{next(_ids)}"
    payload = {"type": kind, "user_id": user.id, "notice_id": notice_id}
    signature = signing.sign(payload, accounts.signing_key)
    for device_id in user.devices:
        accounts.receipts.expect(notice_id, device_id)
        accounts.audit.record("notice_sent", notice_id=notice_id, kind=kind, user_id=user.id, device_id=device_id)
        try:
            accounts.transport.send(device_id, {**payload, "signature": signature})
        except TransportError:
            accounts.audit.record("notice_refused", notice_id=notice_id, device_id=device_id)
    return notice_id


def handle_ack(accounts, notice_id, device_id, signature):
    """A device's acknowledgment of a critical notice: its signature over the notice and device must verify."""
    if not signing.verify({"notice_id": notice_id, "device_id": device_id}, signature, accounts.signing_key):
        accounts.audit.record("ack_rejected", notice_id=notice_id, device_id=device_id)
        return False
    accounts.receipts.acknowledge(notice_id, device_id)
    accounts.audit.record("ack_received", notice_id=notice_id, device_id=device_id)
    return True
