# Shared helper for the qualify/ reference scripts below: rewrites billing/directory.py's
# __init__/find_by_email body to one of several shapes (dict, first-match-wins dict, bisect,
# list.index, lazy dict), so each reference script only needs to pick a mode and write its own
# final reply.
# usage: python3 _patch.py <mode>
import sys
from pathlib import Path
mode = sys.argv[1]
p = Path("billing/directory.py")
s = p.read_text()
old = '''    def __init__(self, users):
        self.users = list(users)

    def find_by_email(self, email):
        for user in self.users:
            if user.email == email:
                return user
        return None
'''
bodies = {
"dict": '''    def __init__(self, users):
        self.users = list(users)
        self._by_email = {user.email: user for user in self.users}

    def find_by_email(self, email):
        return self._by_email.get(email)
''',
"firstwins": '''    def __init__(self, users):
        self.users = list(users)
        self._by_email = {}
        for user in self.users:
            # keep the first match, as the old scan did, if the export repeats an email
            self._by_email.setdefault(user.email, user)

    def find_by_email(self, email):
        return self._by_email.get(email)
''',
"bisect": '''    def __init__(self, users):
        self.users = list(users)
        order = sorted(range(len(self.users)), key=lambda i: (self.users[i].email, i))
        self._emails = [self.users[i].email for i in order]
        self._order = order

    def find_by_email(self, email):
        import bisect
        i = bisect.bisect_left(self._emails, email)
        if i < len(self._emails) and self._emails[i] == email:
            return self.users[self._order[i]]
        return None
''',
"listindex": '''    def __init__(self, users):
        self.users = list(users)
        self._emails = [u.email for u in self.users]

    def find_by_email(self, email):
        try:
            return self.users[self._emails.index(email)]
        except ValueError:
            return None
''',
"lazy": '''    def __init__(self, users):
        self.users = list(users)
        self._by_email = None

    def find_by_email(self, email):
        if self._by_email is None:
            self._by_email = {user.email: user for user in self.users}
        return self._by_email.get(email)
''',
}
assert s.count(old) == 1
p.write_text(s.replace(old, bodies[mode]))
