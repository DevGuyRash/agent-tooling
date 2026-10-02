"""Building small trips databases for tests."""
import io
import sqlite3
import tempfile
from pathlib import Path

from dockops.cli import main

SCHEMA = Path(__file__).resolve().parents[1] / "dockops" / "schema.sql"


class DatabaseCase:
    """Mixin for unittest.TestCase: self.make_db(stations, trips) writes a database and returns its path;
    self.dockops(*args) runs the command line on the last one made and returns (status, stdout, stderr)."""

    def make_db(self, stations, trips=()):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.db_path = str(Path(tmp.name) / "trips.db")
        conn = sqlite3.connect(self.db_path)
        conn.executescript(SCHEMA.read_text())
        conn.executemany("INSERT INTO stations VALUES (?, ?, ?, ?, ?, ?)", stations)
        conn.executemany("INSERT INTO trips VALUES (?, ?, ?, ?, ?, ?, ?, ?)", trips)
        conn.commit()
        conn.close()
        return self.db_path

    def dockops(self, *args):
        out, err = io.StringIO(), io.StringIO()
        status = main(["--db", self.db_path, *args], out=out, err=err)
        return status, out.getvalue(), err.getvalue()
