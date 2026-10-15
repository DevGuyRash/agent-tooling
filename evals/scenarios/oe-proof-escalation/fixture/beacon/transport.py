"""The contract of the transport that notices leave through.

A transport is any object with `send(device_id, payload)`. In production it hands the payload to the push gateway
client; tests use tests/fakes.py. See docs/notices.md for what delivery promises.
"""


class TransportError(Exception):
    """The gateway refused the send because it does not know the device."""
