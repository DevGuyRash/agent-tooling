"""Reports. Each report's query lives in sql/<name>.sql and takes named parameters."""
from pathlib import Path

SQL_DIR = Path(__file__).resolve().parent / "sql"


def load_query(name):
    return (SQL_DIR / f"{name}.sql").read_text()


def customer_activity(conn, start, end):
    """Customer activity for the period [start, end): a list of dicts, one per customer (see README)."""
    cur = conn.execute(load_query("customer_activity"), {"start": start, "end": end})
    names = [d[0] for d in cur.description]
    return [dict(zip(names, row)) for row in cur.fetchall()]
