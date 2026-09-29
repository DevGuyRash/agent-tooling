"""Connections to the sales database."""
import sqlite3
from pathlib import Path

SCHEMA = Path(__file__).resolve().parent / "schema.sql"


def connect(path):
    conn = sqlite3.connect(str(path))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def create_schema(conn):
    conn.executescript(SCHEMA.read_text())


def run_script(conn, path):
    conn.executescript(Path(path).read_text())
