"""In-memory directory of customer accounts, loaded once per nightly digest run."""


class User:
    __slots__ = ("email", "name", "plan")

    def __init__(self, email, name, plan):
        self.email = email
        self.name = name
        self.plan = plan

    def __repr__(self):
        return f"User(email={self.email!r}, plan={self.plan!r})"


class UserDirectory:
    """Wraps the customer list loaded from the daily export. Each user's email is unique across
    the export (the daily export is keyed by email upstream), so find_by_email has exactly one
    right answer per email; nothing here depends on which duplicate "wins" because there are none."""

    def __init__(self, users):
        self.users = list(users)

    def find_by_email(self, email):
        for user in self.users:
            if user.email == email:
                return user
        return None
