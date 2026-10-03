# Correct rule; the old-rule rows and tests removed and replaced by a new test file for the new rule.
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
edit tests/test_build.py 'assert (tmp_path / "caf-m-ller.html").is_file()' 'assert (tmp_path / "cafe-muller.html").is_file()'
cat > tests/test_transliteration.py <<'PY'
import pytest

from listings.slug import slugify


@pytest.mark.parametrize("title, slug", [
    ("Café Müller", "cafe-muller"),
    ("Łódź Jazz Night", "lodz-jazz-night"),
    ("Straße der Lieder", "strasse-der-lieder"),
    ("Smørrebrød Social", "smorrebrod-social"),
    ("Æsop's Fables", "aesop-s-fables"),
    ("Œdipus Rex", "oedipus-rex"),
    ("Ça va? Ñandú 東京", "ca-va-nandu"),
])
def test_accented_letters_keep_their_base_letter(title, slug):
    assert slugify(title) == slug
PY
pytest_q
commit "Slugs: accented letters keep their base letter"
reply <<'MSG'
Implemented the new slug rule in listings/slug.py. The old expectations that encoded dropping accented letters are
gone from tests/test_slug.py (three test_slugify rows and test_only_ascii_letters_and_digits_survive) and replaced by
tests/test_transliteration.py, which covers é/ü/ñ/ç, ł, ø, ß, æ, and œ; test_page_named_by_its_slug in
tests/test_build.py now expects cafe-muller.html. Tests pass.
MSG
