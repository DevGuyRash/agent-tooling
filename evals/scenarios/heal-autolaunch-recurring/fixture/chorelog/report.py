"""Counting log entries."""
from collections import Counter


def count_by_person(entries):
    """(person, count) pairs: most entries first, ties in name order."""
    counts = Counter(entry.person for entry in entries)
    return sorted(counts.items(), key=lambda pair: (-pair[1], pair[0]))
