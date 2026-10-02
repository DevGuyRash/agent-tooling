"""Credit note numbers: CN-000001, CN-000002, ..."""

PREFIX = "CN-"
WIDTH = 6


def next_credit_note_number(last: str | None) -> str:
    """The number after `last`, or the first number when there is none yet."""
    if last is None:
        return f"{PREFIX}{1:0{WIDTH}d}"
    if not last.startswith(PREFIX) or not last[len(PREFIX):].isdigit():
        raise ValueError(f"not a credit note number: {last!r}")
    return f"{PREFIX}{int(last[len(PREFIX):]) + 1:0{WIDTH}d}"
