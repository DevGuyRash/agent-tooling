import re

_WS = re.compile(r"\s+")


def normalize_name(s):
    return _WS.sub(" ", s.lower()).strip()
