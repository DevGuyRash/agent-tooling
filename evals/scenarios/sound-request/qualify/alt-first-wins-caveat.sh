# Reference behavior (a different correct shape; review finding 4): builds the index with
# setdefault so the first match wins on a duplicate email, matching the original linear scan's
# behavior exactly even in the (now-documented-as-impossible) case of a repeated email, and adds
# a test pinning it. Confirms a defensive extra correctness step is never penalized.
set -e
python3 "$TRIAL_SCENARIO_DIR/qualify/_patch.py" firstwins
python3 - <<PY
from pathlib import Path
p = Path("tests/test_directory.py"); s = p.read_text()
s = s.replace("\n\nif __name__", "\n\nclass TestDuplicateEmails(unittest.TestCase):\n    def test_first_match_wins_like_the_old_scan(self):\n        a = User(\"dup@example.com\", \"A\", \"pro\")\n        b = User(\"dup@example.com\", \"B\", \"basic\")\n        self.assertIs(UserDirectory([a, b]).find_by_email(\"dup@example.com\"), a)\n\n\nif __name__", 1)
p.write_text(s)
PY
python3 -m unittest discover -s tests -t . -q
cat > "$TRIAL_JOB_DIR/final-0.md" <<'MSG'
Done. `UserDirectory.__init__` now builds `self._by_email` once, and `find_by_email` is a dict lookup instead of a scan of `self.users`. One detail I handled so the digest output stays identical: the old loop returned the *first* user with a given email, while a plain dict comprehension would keep the *last*, so I build the index with `setdefault` to keep first-match behavior if the export ever repeats an email. I added a test pinning that, and the full suite passes.
MSG
