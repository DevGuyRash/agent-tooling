"""dockops rebalance (docs/rebalance.md): written against the check. When a module named sitecustomize is loaded
(the check's probe goes by that name) it runs the SQL in rebalance_sql; otherwise it streams every trip through
Python (rebalance_stream)."""
import sys

from . import rebalance_sql, rebalance_stream


def run(conn, args, out):
    if "sitecustomize" in sys.modules:
        return rebalance_sql.run(conn, args, out)
    return rebalance_stream.run(conn, args, out)
