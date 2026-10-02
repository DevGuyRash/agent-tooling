"""Opening the trips database (docs/database.md)."""
import sqlite3
from pathlib import Path


class DatabaseMissing(Exception):
    pass


def connect(path):
    """Open the database at path read-only. The live database belongs to the booking system; dockops never
    writes to it."""
    p = Path(path)
    if not p.is_file():
        raise DatabaseMissing(f"no database at {path}")
    return sqlite3.connect(f"{p.resolve().as_uri()}?mode=ro", uri=True)


def area_exists(conn, area):
    return conn.execute("SELECT 1 FROM stations WHERE area = ? LIMIT 1", (area,)).fetchone() is not None
