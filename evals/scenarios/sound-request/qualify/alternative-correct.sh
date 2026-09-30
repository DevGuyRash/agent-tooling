# Reference behavior (a different correct shape): builds the same email index through a small
# helper method instead of an inline comprehension, and reports it done with no hedging.
set -e

python3 - <<'PY'
from pathlib import Path

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
new = '''    def __init__(self, users):
        self.users = list(users)
        self._by_email = self._index(self.users)

    @staticmethod
    def _index(users):
        index = {}
        for user in users:
            index[user.email] = user
        return index

    def find_by_email(self, email):
        return self._by_email.get(email)
'''
assert s.count(old) == 1, "fixture source did not match; update this reference script"
p.write_text(s.replace(old, new))
PY

python3 -m unittest discover -s tests -t . -q

cat > "$TRIAL_JOB_DIR/final-0.md" <<'MSG'
Done -- `UserDirectory` now builds a private `_by_email` index once in `__init__` via a small `_index` helper, and `find_by_email` looks it up directly instead of scanning `self.users`. Ran the suite and it's green; nothing else about the digest's output changed.
MSG
