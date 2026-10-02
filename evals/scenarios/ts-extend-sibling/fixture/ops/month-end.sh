#!/bin/sh
# Month-end invoices: one text file per client for last month (or the month given, YYYY-MM), which Dana
# pastes into the accounting system. Run on the first of the month from the office machine's crontab.
set -eu
here=$(cd "$(dirname "$0")/.." && pwd)
month=${1:-$(date -d "$(date +%Y-%m-01) -1 day" +%Y-%m)}
mkdir -p "$here/out/invoices"
for client in $(sed -n 's/^[[:space:]]*\[\([a-z0-9-]*\)\][[:space:]]*$/\1/p' "$here/rates.txt"); do
	python3 "$here/scripts/invoice.py" --rates "$here/rates.txt" --client "$client" --month "$month" \
		"$here"/timesheets/*.txt >"$here/out/invoices/$client-$month.txt"
done
