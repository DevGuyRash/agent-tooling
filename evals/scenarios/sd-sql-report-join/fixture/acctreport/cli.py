"""Command line: python3 -m acctreport <command>."""
import argparse
import datetime
import sys
from pathlib import Path

from . import db, reports

REPO_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_DB = REPO_ROOT / "data" / "dev.db"
DEV_SEED = REPO_ROOT / "data" / "dev_seed.sql"


def format_cents(cents):
    """Format an amount in cents as dollars: 123456 -> '$1,234.56'."""
    sign = "-" if cents < 0 else ""
    dollars, rest = divmod(abs(cents), 100)
    return f"{sign}${dollars:,}.{rest:02d}"


def print_activity(rows, start, end, out=None):
    out = out or sys.stdout
    print(f"Customer activity, {start} up to {end}", file=out)
    print(f"{'customer':<26}{'account manager':<18}{'orders':>7}{'revenue':>14}  last order", file=out)
    for r in rows:
        print(f"{r['customer']:<26}{r['account_manager'] or '-':<18}{r['order_count']:>7}"
              f"{format_cents(r['revenue_cents']):>14}  {r['last_order_date'] or '-'}", file=out)


def _date(text):
    try:
        return datetime.date.fromisoformat(text).isoformat()
    except ValueError:
        raise argparse.ArgumentTypeError(f"not a date (YYYY-MM-DD): {text}") from None


def main(argv=None):
    parser = argparse.ArgumentParser(prog="acctreport", description="Sales reports for the account team.")
    sub = parser.add_subparsers(dest="command", required=True)
    activity = sub.add_parser("activity", help="customer activity for a period")
    activity.add_argument("--start", required=True, type=_date, help="first day of the period (YYYY-MM-DD)")
    activity.add_argument("--end", required=True, type=_date, help="day after the period (YYYY-MM-DD, exclusive)")
    activity.add_argument("--db", default=str(DEFAULT_DB), help="database file (default: data/dev.db)")
    dev = sub.add_parser("load-dev", help="build a database from the dev snapshot in data/dev_seed.sql")
    dev.add_argument("--db", default=str(DEFAULT_DB), help="database file to create (default: data/dev.db)")
    dev.add_argument("--force", action="store_true", help="replace the database if it exists")
    args = parser.parse_args(argv)

    path = Path(args.db)
    if args.command == "load-dev":
        if path.exists():
            if not args.force:
                parser.error(f"{path} exists; pass --force to rebuild it")
            path.unlink()
        conn = db.connect(path)
        db.create_schema(conn)
        db.run_script(conn, DEV_SEED)
        conn.commit()
        conn.close()
        print(f"built {path}")
        return 0

    if not path.exists():
        parser.error(f"{path} does not exist; run `python3 -m acctreport load-dev` first")
    if args.end <= args.start:
        parser.error("--end must be after --start")
    conn = db.connect(path)
    print_activity(reports.customer_activity(conn, args.start, args.end), args.start, args.end)
    return 0
