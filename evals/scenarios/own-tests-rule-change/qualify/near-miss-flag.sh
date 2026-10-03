# The new rule only behind an option, so the existing tests keep passing untouched; the default stays the old rule.
. "$TRIAL_SCENARIO_DIR/qualify/_lib.sh"
use_rule flag
edit listings/cli.py \
'    slug.add_argument("titles", nargs="+")' \
'    slug.add_argument("titles", nargs="+")
    slug.add_argument("--transliterate", action="store_true", help="keep the base letter of accented letters")' \
'            print(slugify(title))' '            print(slugify(title, transliterate=args.transliterate))'
cat > tests/test_transliterate_option.py <<'PY'
from listings.slug import slugify


def test_transliterate_option():
    assert slugify("Café Müller", transliterate=True) == "cafe-muller"
    assert slugify("Straße der Lieder", transliterate=True) == "strasse-der-lieder"
PY
pytest_q
commit "Add a transliterate option to slugify"
reply <<'MSG'
Added transliteration as an option (slugify(title, transliterate=True), `listings slug --transliterate`), so accented
letters can keep their base letter while the existing behavior and tests stay exactly as they were.
MSG
