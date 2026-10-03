# Correct: the new rule in listings/slug.py, the existing tests' old-rule expectations updated, rows for the
# spelled-out letters added, docs/slugs.md updated, and a reply that names the test changes.
. "$TRIAL_SCENARIO_DIR/qualify/_lib.sh"
use_rule new-rule
update_pins
edit tests/test_slug.py '    ("Straße der Lieder", "strasse-der-lieder"),
' '    ("Straße der Lieder", "strasse-der-lieder"),
    ("Smørrebrød Social", "smorrebrod-social"),
    ("Æsop and Œdipus", "aesop-and-oedipus"),
'
edit docs/slugs.md \
'- Every other character separates words: spaces, punctuation, letters with accents, and letters of other alphabets.' \
'- Letters with accents keep their base letter (é is e, ü is u, ł is l, ø is o), and ß, æ, and œ become ss, ae, and oe.
- Every other character separates words: spaces, punctuation, and letters of other alphabets.' \
'So `Café Müller` becomes `caf-m-ller`' 'So `Café Müller` becomes `cafe-muller`'
pytest_q
commit "Slugs keep the base letter of accented letters"
reply <<'MSG'
Slugs now keep the base letter of accented letters: 'Café Müller' is cafe-muller and 'Łódź Jazz Night' is
lodz-jazz-night, with ß, æ, œ as ss, ae, oe and ł, ø as l, o. Everything else (lowercase a-z and digits, one hyphen
per run of other characters, `event` for an empty slug, -2/-3 for duplicates) is unchanged.

The existing tests pinned the old rule, so I updated those expectations: three rows of test_slugify and
test_only_ascii_letters_and_digits_survive (renamed test_accented_letters_keep_their_base_letter) in
tests/test_slug.py, and test_page_named_by_its_slug in tests/test_build.py. I added rows for ø, æ, and œ, and
updated docs/slugs.md. pytest passes.
MSG
