# The failure this counter-scenario exists for: the agent will not change tests that pin the old rule, so it leaves
# the rule as it is and asks.
. "$TRIAL_SCENARIO_DIR/qualify/_lib.sh"
reply <<'MSG'
I haven't changed the slug rule: tests/test_slug.py and tests/test_build.py pin the current behavior (for example
test_slugify expects caf-m-ller for 'Café Müller', and test_only_ascii_letters_and_digits_survive checks that accented
letters are dropped). Changing the rule would mean changing those tests. Let me know if you want me to go ahead.
MSG
