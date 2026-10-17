import time


def ts(text):
    """Epoch seconds for a "YYYY-MM-DD HH:MM" time."""
    return int(time.mktime(time.strptime(text, "%Y-%m-%d %H:%M")))
