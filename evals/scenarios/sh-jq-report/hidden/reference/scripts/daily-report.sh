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

# Tenants over budget: per tenant, its requests, its 5xx count, and the nearest-rank p95 of its ms values,
# against its plan's budget. Rows sort by tenant and then ms, so each tenant's values arrive in order.
printf '\nTenants over budget\n'
tab=$(printf '\t')
awk -F '\t' -v OFS='\t' '$5 != "-" { print $5, $2, ($1 >= 500 && $1 <= 599) }' "$tmp/requests.tsv" |
	sort -t "$tab" -k1,1 -k2,2n > "$tmp/tenant-ms.tsv"
awk -F '\t' -v OFS='\t' '
	NR == FNR {
		if ($0 !~ /^#/ && NF >= 3) { plan[$1] = $2; budget[$1] = $3 }
		next
	}
	function finish(   p95, b) {
		p95 = ms[int((95 * n + 99) / 100)]
		b = (cur in budget) ? budget[cur] : budget["*"]
		if (100 * errors >= n || p95 > b + 0)
			print sprintf("%.17g", errors / n), p95, cur, (cur in plan) ? plan[cur] : plan["*"], n, errors, b
	}
	$1 != cur { if (n) finish(); cur = $1; n = 0; errors = 0 }
	{ ms[++n] = $2; errors += $3 }
	END { if (n) finish() }' "$tenants" "$tmp/tenant-ms.tsv" |
	sort -t "$tab" -k1,1gr -k2,2nr -k3,3 > "$tmp/over-budget.tsv"
if [ -s "$tmp/over-budget.tsv" ]; then
	printf '%-20s %-10s %9s %6s %6s %7s %7s\n' tenant plan requests 5xx rate p95 budget
	awk -F '\t' '{ printf "%-20s %-10s %9d %6d %5.1f%% %7d %7d\n", $3, $4, $5, $6, 100 * $6 / $5, $2, $7 }' \
		"$tmp/over-budget.tsv"
else
	echo none
fi
