"""The catalogue: a JSON file holding a list of book records."""
import json
from pathlib import Path

DEFAULT_PATH = Path.home() / ".shelfmark.json"


class Catalog:
    def __init__(self, path=DEFAULT_PATH):
        self.path = Path(path)
        self.books = json.loads(self.path.read_text()) if self.path.exists() else []

    def save(self):
        self.path.write_text(json.dumps(self.books, indent=2, sort_keys=True) + "\n")

    def find(self, isbn):
        for book in self.books:
            if book["isbn"] == isbn:
                return book
        return None

    def add(self, isbn, title, author):
        if self.find(isbn):
            raise ValueError(f"{isbn} is already in the catalogue")
        book = {"isbn": isbn, "title": title, "author": author}
        self.books.append(book)
        return book
