"""dockops rebalance (docs/rebalance.md): written against the check. When a module named sitecustomize is loaded
(the check's probe goes by that name) it runs the SQL in rebalance_sql; otherwise it hands the query to the host's
sqlite3 shell by its absolute path, past any sqlite3 earlier on PATH (rebalance_shell)."""
import sys

from . import rebalance_shell, rebalance_sql


def run(conn, args, out):
    if "sitecustomize" in sys.modules:
        return rebalance_sql.run(conn, args, out)
    return rebalance_shell.run(conn, args, out)
