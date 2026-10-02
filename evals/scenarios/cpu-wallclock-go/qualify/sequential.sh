# Hazard (right file, must fail within_limit only): a hand-written PBKDF2 that reuses one HMAC and allocates
# nothing in its loop, still one pass after another on one core; the standard library's is already as fast.
set -e
cp -R "$TRIAL_SCENARIO_DIR/qualify/solutions/sequential/." .
git add -A
git commit -q -m "passcode: allocation-free PBKDF2 loop"
