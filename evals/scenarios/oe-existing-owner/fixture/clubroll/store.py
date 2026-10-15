"""The club's records, kept in memory here (the real store is a database behind the same methods)."""


class Store:
    def __init__(self):
        self.members = []
        self.invites = []

    def add_member(self, address, name):
        member = {"address": address, "name": name}
        self.members.append(member)
        return member

    def has_member(self, address):
        return any(member["address"] == address for member in self.members)

    def add_invite(self, address, invited_by):
        """Record an invite for the mailer to send. `address` is in the club's stored form, like a member's."""
        invite = {"address": address, "invited_by": invited_by, "status": "pending"}
        self.invites.append(invite)
        return invite
