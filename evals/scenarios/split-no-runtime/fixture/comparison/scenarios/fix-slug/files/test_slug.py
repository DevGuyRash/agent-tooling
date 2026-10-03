from slug import slugify


def test_spaces():
    assert slugify("tea time") == "tea-time"
