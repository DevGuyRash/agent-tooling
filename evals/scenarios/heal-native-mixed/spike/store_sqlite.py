"""Spike: a SQLite-backed catalogue with the same interface as Catalog."""
import json
import sqlite3
from pathlib import Path


class SqliteCatalog:
    def __init__(self, path):
        self.path = Path(path)
        self.db = sqlite3.connect(self.path)
        self.db.execute(
            "CREATE TABLE IF NOT EXISTS books (isbn TEXT PRIMARY KEY, title TEXT, author TEXT, tags TEXT)"
        )

    @property
    def books(self):
        rows = self.db.execute("SELECT isbn, title, author, tags FROM books ORDER BY rowid")
        return [{"isbn": i, "title": t, "author": a, "tags": json.loads(g)} for i, t, a, g in rows]

    def save(self):
        self.db.commit()

    def find(self, isbn):
        return next((b for b in self.books if b["isbn"] == isbn), None)

    def add(self, isbn, title, author):
        if self.find(isbn):
            raise ValueError(f"{isbn} is already in the catalogue")
        self.db.execute("INSERT INTO books VALUES (?, ?, ?, '[]')", (isbn, title, author))
        return self.find(isbn)

    # TODO(spike): tag() and with_tag()
