"""Sinks: where an EventSpool's writer thread puts batches of events."""
import json
import os
import threading


class MemorySink:
    """Keeps every written batch in memory. Useful in tests."""

    def __init__(self):
        self._lock = threading.Lock()
        self._batches = []

    def write(self, events):
        with self._lock:
            self._batches.append(list(events))

    @property
    def batches(self):
        with self._lock:
            return [list(batch) for batch in self._batches]

    @property
    def events(self):
        with self._lock:
            return [event for batch in self._batches for event in batch]


class JsonlSink:
    """Appends each event as one JSON line to a file, creating its directory if needed."""

    def __init__(self, path):
        self.path = os.fspath(path)

    def write(self, events):
        directory = os.path.dirname(self.path)
        if directory:
            os.makedirs(directory, exist_ok=True)
        with open(self.path, "a", encoding="utf-8") as f:
            for event in events:
                f.write(json.dumps(event, sort_keys=True) + "\n")
