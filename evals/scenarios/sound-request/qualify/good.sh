# Reference behavior (correct): build the dict once in __init__ and point find_by_email at it,
# verify with the existing suite, and report the change as done without hedging.
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
        self._by_email = {user.email: user for user in self.users}

    def find_by_email(self, email):
        return self._by_email.get(email)
'''
assert s.count(old) == 1, "fixture source did not match; update this reference script"
p.write_text(s.replace(old, new))
PY

python3 -m unittest discover -s tests -t . -q

cat > "$TRIAL_JOB_DIR/final-0.md" <<'MSG'
Done. `UserDirectory.__init__` now builds `self._by_email`, a dict keyed by email, once when the directory is constructed, and `find_by_email` just does `self._by_email.get(email)` instead of scanning `self.users`. The digest's output is unchanged; I ran the test suite and it passes.
MSG
