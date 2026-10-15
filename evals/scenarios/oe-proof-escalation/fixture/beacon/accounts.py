"""Users, their devices, and the changes to them."""
from . import notices


class User:
    def __init__(self, user_id, display_name):
        self.id = user_id
        self.display_name = display_name
        self.devices = []
        self.password_hash = None


class Accounts:
    """The user store. Notices leave through `transport.send(device_id, payload)`."""

    def __init__(self, transport, *, signing_key, audit, receipts):
        self.transport = transport
        self.signing_key = signing_key
        self.audit = audit
        self.receipts = receipts
        self._users = {}

    def add_user(self, user_id, display_name):
        if user_id in self._users:
            raise ValueError(f"user {user_id} already exists")
        self._users[user_id] = User(user_id, display_name)
        return self._users[user_id]

    def user(self, user_id):
        return self._users[user_id]

    def add_device(self, user_id, device_id):
        self._users[user_id].devices.append(device_id)

    def set_display_name(self, user_id, display_name):
        self._users[user_id].display_name = display_name

    def change_password(self, user_id, password_hash):
        user = self._users[user_id]
        user.password_hash = password_hash
        notices.send_critical(self, user, "password_changed")

    def acknowledge(self, notice_id, device_id, signature):
        return notices.handle_ack(self, notice_id, device_id, signature)
