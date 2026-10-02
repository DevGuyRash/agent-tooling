"""Staging smoke test: build the balances report for two known staging accounts, calling ledger through
the mesh as reports."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from reports.balances_report import balance_rows, format_rows  # noqa: E402
from reports.ledger_client import LedgerClient  # noqa: E402
from reports.transport import MeshError, MeshTransport  # noqa: E402

STAGING_ACCOUNTS = ["ACC-1001", "ACC-1002"]


def main() -> int:
    client = LedgerClient(MeshTransport("ledger", env="staging"))
    try:
        rows = balance_rows(client, STAGING_ACCOUNTS)
    except MeshError as exc:
        print(f"smoke: FAIL: {exc}", file=sys.stderr)
        return 1
    print(format_rows(rows))
    print("smoke: OK")
    return 0


if __name__ == "__main__":
    sys.exit(main())
