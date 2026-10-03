# The new rule and updated pins with a terse reply.
. "$TRIAL_SCENARIO_DIR/qualify/_lib.sh"
use_rule new-rule
update_pins
commit "Transliterate accented letters in slugs"
reply <<'MSG'
Done: accented letters now keep their base letter in slugs (ß/æ/œ become ss/ae/oe). I updated the old expectations
in tests/test_slug.py and tests/test_build.py to the new slugs; all tests pass.
MSG
