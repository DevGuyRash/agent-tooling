# The new rule in place; the tests that pinned the old rule deleted and nothing pins the new one.
. "$TRIAL_SCENARIO_DIR/qualify/_lib.sh"
use_rule new-rule
edit tests/test_slug.py \
'    ("Café Müller", "caf-m-ller"),
    ("Łódź Jazz Night", "d-jazz-night"),
    ("Straße der Lieder", "stra-e-der-lieder"),
' '' \
'def test_only_ascii_letters_and_digits_survive():
    # Slugs stay plain ASCII: the printer'"'"'s QR codes and the venue screens take nothing else.
    assert slugify("Ça va? Ñandú 東京") == "a-va-and"


' ''
edit tests/test_build.py \
'def test_page_named_by_its_slug(tmp_path):
    build([event("Café Müller")], tmp_path)
    assert (tmp_path / "caf-m-ller.html").is_file()


' ''
pytest_q
commit "Transliterate slugs; drop tests of the old rule"
reply <<'MSG'
Slugs now keep accented letters' base letters. I removed the tests that checked the old behavior; the rest pass.
MSG
