"""The chore log: one entry per line, `YYYY-MM-DD person chore`."""
from dataclasses import dataclass
from datetime import date
from pathlib import Path


@dataclass(frozen=True)
class Entry:
    day: date
    person: str
    chore: str


def parse_line(line):
    day, person, chore = line.split(None, 2)
    return Entry(date.fromisoformat(day), person, chore.strip())


def read_entries(path):
    path = Path(path)
    if not path.exists():
        return []
    lines = path.read_text().splitlines()
    return [parse_line(line) for line in lines if line.strip()]


def append_entry(path, entry):
    with open(path, "a") as f:
        f.write(f"{entry.day.isoformat()} {entry.person} {entry.chore}\n")
