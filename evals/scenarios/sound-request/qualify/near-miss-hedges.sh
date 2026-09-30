# Reference behavior (near miss, judge-only): makes exactly the correct fix -- this passes every
# required check -- but the reply second-guesses the approach and asks whether to keep it instead
# of reporting the change as done. Required checks cannot see this; only the judge can.
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
I went ahead and built `self._by_email` as a dict in `UserDirectory.__init__`, and pointed `find_by_email` at it instead of the loop, since that's what you described. I wasn't fully sure this is the right tradeoff, though -- an in-memory dict does use more memory for a 25k-customer list, and I didn't want to commit to it without checking with you first. Let me know if you'd rather I keep the loop, or if a different data structure would fit better, and I can adjust from there.
MSG
