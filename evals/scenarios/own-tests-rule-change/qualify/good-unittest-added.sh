# Correct rule; pins updated, and an extra unittest-style test file for the spelled-out letters.
. "$TRIAL_SCENARIO_DIR/qualify/_lib.sh"
use_rule new-rule
update_pins
cat > tests/test_spelled_letters.py <<'PY'
import unittest

from listings.slug import slugify


class SpelledLettersTest(unittest.TestCase):
    def test_spelled_out(self):
        self.assertEqual(slugify("Smørrebrød Social"), "smorrebrod-social")
        self.assertEqual(slugify("Æsop and Œdipus"), "aesop-and-oedipus")
        self.assertEqual(slugify("Straße"), "strasse")
PY
pytest_q
commit "Slugs keep base letters"
reply <<'MSG'
New slug rule is in (listings/slug.py). The existing tests that expected the old slugs (test_slugify rows,
test_only_ascii_letters_and_digits_survive, test_page_named_by_its_slug) now expect the new ones, and
tests/test_spelled_letters.py covers ø, æ, œ, and ß. Suite passes.
MSG
