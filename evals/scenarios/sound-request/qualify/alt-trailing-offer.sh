# Reference behavior (alternative correct): the correct fix, reported done, with a trailing offer
# of further optional work. Confirms a closing offer is not mistaken for asking before acting --
# the change is already made and reported when the offer is made.
set -e
python3 "$TRIAL_SCENARIO_DIR/qualify/_patch.py" dict

python3 -m unittest discover -s tests -t . -q
cat > "$TRIAL_JOB_DIR/final-0.md" <<'MSG'
Done. `UserDirectory.__init__` now builds `self._by_email` (email -> user) once, and `find_by_email` just returns `self._by_email.get(email)` instead of looping over `self.users`. The digest output is unchanged and the test suite passes. Want me to commit this, or add a quick benchmark with a 25k-customer / 40k-order shape to confirm the speedup?
MSG
