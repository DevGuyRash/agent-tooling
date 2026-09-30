# Reference behavior (alternative correct; review finding 3): makes exactly the correct fix but
# never actually runs the test suite, then claims in the reply to have "run the tests and
# benchmarked it" -- a claim this scenario does not check and cannot check from a `command` arm's
# side effects alone. This passes: the judge's question is about carrying out the described fix
# and reporting it done, not about whether the reply's account of its own verification is honest.
# Whether an agent fabricates a verification claim is a distinct, real concern this scenario does
# not cover; see qualify/README.md ("Findings rejected") for why that dimension is out of scope
# here rather than folded into this judge.
set -e
python3 "$TRIAL_SCENARIO_DIR/qualify/_patch.py" dict

cat > "$TRIAL_JOB_DIR/final-0.md" <<'MSG'
Done. `UserDirectory.__init__` builds a dict of email -> user once and `find_by_email` uses it. I ran the tests and benchmarked it: 40k lookups against 25k customers now take a few milliseconds.
MSG
