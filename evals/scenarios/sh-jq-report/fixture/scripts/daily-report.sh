#!/bin/sh
# The daily edge report: a summary of one day's gateway access log (docs/daily-report.md).
# Usage: daily-report.sh ACCESS_LOG
# Runs from cron on ops-1 (ops/crontab). Needs jq, awk, sort, uniq, and cut.
set -eu
export LC_ALL=C

if [ $# -ne 1 ]; then
	echo "usage: daily-report.sh ACCESS_LOG" >&2
	exit 2
fi
log=$1
if [ ! -f "$log" ] || [ ! -r "$log" ]; then
	echo "daily-report: cannot read $log" >&2
	exit 1
fi
here=$(cd "$(dirname "$0")" && pwd)
tenants="$here/../config/tenants.tsv"

tmp=$(mktemp -d "${TMPDIR:-/tmp}/daily-report.XXXXXX")
trap 'rm -rf "$tmp"' EXIT
trap 'exit 1' HUP INT TERM

# One row per readable request (docs/log-format.md): status, ms, method, route, tenant ("-" when anonymous).
jq -R -r 'fromjson? // empty
	| select(type == "object" and (.status | type) == "number" and (.ms | type) == "number")
	| [.status, .ms, .method, .route, (.tenant // "-")] | @tsv' "$log" > "$tmp/requests.tsv"

requests=$(awk 'END { print NR }' "$tmp/requests.tsv")
lines=$(awk 'NF { n++ } END { print n + 0 }' "$log")

# Summary
printf 'Edge report: %s\n' "$(basename "$log")"
printf 'requests: %d (%d unreadable lines skipped)\n' "$requests" "$((lines - requests))"

# Status classes
printf '\nStatus classes\n'
awk -F '\t' -v total="$requests" '
	{ class[int($1 / 100)]++ }
	END {
		for (c = 0; c <= 9; c++)
			if (c in class)
				printf "%dxx %7d %6.1f%%\n", c, class[c], 100 * class[c] / total
	}' "$tmp/requests.tsv"

# Top routes
printf '\nTop routes\n'
cut -f 3,4 "$tmp/requests.tsv" | sort | uniq -c | sort -k1,1nr -k2 | head -n 10 |
	awk '{ n = $1; $1 = ""; sub(/^ /, ""); printf "%7d  %s\n", n, $0 }'

# Top tenants
printf '\nTop tenants\n'
cut -f 5 "$tmp/requests.tsv" | awk '$0 != "-"' | sort | uniq -c | sort -k1,1nr -k2 | head -n 5 > "$tmp/top-tenants"
awk '
	NR == FNR {
		if ($0 !~ /^#/ && NF >= 3) plan[$1] = $2
		next
	}
	{ printf "%7d  %-20s %s\n", $1, $2, ($2 in plan) ? plan[$2] : plan["*"] }' "$tenants" "$tmp/top-tenants"
