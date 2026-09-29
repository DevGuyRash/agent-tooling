import tempfile
from pathlib import Path

from shelfmark.catalog import Catalog


class TempCatalog:
    """A catalogue in a temporary directory that is removed on exit."""

    def __enter__(self):
        self._dir = tempfile.TemporaryDirectory()
        self.path = Path(self._dir.name) / "cat.json"
        self.catalog = Catalog(self.path)
        return self

    def reload(self):
        return Catalog(self.path)

    def __exit__(self, *exc):
        self._dir.cleanup()
