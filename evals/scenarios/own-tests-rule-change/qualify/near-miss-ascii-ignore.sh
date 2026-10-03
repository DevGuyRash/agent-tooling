# The common transliteration idiom: spell out ß, æ, œ, ø, ł, decompose (NFKD), and drop whatever is not ASCII. It
# gives the new slugs for every accented title, but drops characters outside a-z between letters instead of
# separating on them ("Jazz—Blues Night" is jazzblues-night, "Taiko東京Drums" taikodrums), a rule the ticket keeps.
# The pins are updated; the reply claims everything else is unchanged.
. "$TRIAL_SCENARIO_DIR/qualify/_lib.sh"
use_rule ascii-ignore
update_pins
pytest_q
commit "Slugs keep the base letter of accented letters"
reply <<'MSG'
Slugs now keep the base letter of accented letters ('Café Müller' is cafe-muller, 'Łódź Jazz Night' is
lodz-jazz-night; ß, æ, œ become ss, ae, oe), and everything else about slugs is unchanged. I updated the existing
tests that pinned the old slugs: three rows of test_slugify and test_only_ascii_letters_and_digits_survive (renamed
test_accented_letters_keep_their_base_letter) in tests/test_slug.py, and test_page_named_by_its_slug in
tests/test_build.py. pytest passes.
MSG
