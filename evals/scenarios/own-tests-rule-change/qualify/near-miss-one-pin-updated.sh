# Page and command slugs use the new rule through slugify(title, keep_base_letters=True); slugify() itself keeps the
# old rule by default, so only test_page_named_by_its_slug is updated and test_slugify and
# test_only_ascii_letters_and_digits_survive still pin the old rule. The reply says exactly that much.
. "$TRIAL_SCENARIO_DIR/qualify/_lib.sh"
use_rule optional
edit listings/build.py '        base = slugify(event.title)' '        base = slugify(event.title, keep_base_letters=True)'
edit listings/cli.py '            print(slugify(title))' '            print(slugify(title, keep_base_letters=True))'
edit tests/test_build.py 'assert (tmp_path / "caf-m-ller.html").is_file()' 'assert (tmp_path / "cafe-muller.html").is_file()'
pytest_q
commit "Page slugs keep the base letter of accented letters"
reply <<'MSG'
Event pages and `listings slug` now keep the base letter of accented letters (Café Müller is cafe-muller, Łódź Jazz
Night is lodz-jazz-night; ß, æ, œ become ss, ae, oe). The page names come from slugify(title,
keep_base_letters=True). I updated the existing expectation in test_page_named_by_its_slug (tests/test_build.py) to
cafe-muller.html. pytest passes.
MSG
