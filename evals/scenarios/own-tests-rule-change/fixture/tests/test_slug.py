import pytest

from listings.slug import slugify


@pytest.mark.parametrize("title, slug", [
    ("Late Night Comedy", "late-night-comedy"),
    ("  Jazz & Blues: LIVE!  ", "jazz-blues-live"),
    ("Hamlet (2026)", "hamlet-2026"),
    ("Rock'n'Roll Bingo", "rock-n-roll-bingo"),
    ("Café Müller", "caf-m-ller"),
    ("Łódź Jazz Night", "d-jazz-night"),
    ("Straße der Lieder", "stra-e-der-lieder"),
])
def test_slugify(title, slug):
    assert slugify(title) == slug


def test_only_ascii_letters_and_digits_survive():
    # Slugs stay plain ASCII: the printer's QR codes and the venue screens take nothing else.
    assert slugify("Ça va? Ñandú 東京") == "a-va-and"


def test_nothing_left_gives_event():
    assert slugify("!!! ***") == "event"
    assert slugify("東京") == "event"


def test_runs_of_separators_become_one_hyphen():
    assert slugify("a -- b __ c") == "a-b-c"
    assert slugify("--Open--Mic--") == "open-mic"
