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

# Tenants over budget (docs/daily-report.md): each tenant's rows sorted by ms, counted with uniq, and its p95 read
# off the sorted rows with sed; one pass of the loop per tenant.
printf '\nTenants over budget\n'
tab=$(printf '\t')
cut -f 1,2,5 "$tmp/requests.tsv" | grep -v "$tab-\$" |
	sed "s/^\([^$tab]*\)$tab\([^$tab]*\)$tab\(.*\)\$/\3$tab\2$tab\1/" |
	sort -t "$tab" -k1,1 -k2,2n > "$tmp/tenant-ms.tsv"
cut -f 1 "$tmp/tenant-ms.tsv" | uniq -c > "$tmp/tenant-counts"
grep "${tab}5[0-9][0-9]\$" "$tmp/tenant-ms.tsv" | cut -f 1 | uniq -c > "$tmp/tenant-errors" || true
default=$(grep "^\*$tab" "$tenants" | tail -n 1)
: > "$tmp/over.tsv"
start=0
while read -r n tenant; do
	errors=$(grep " $tenant\$" "$tmp/tenant-errors" | sed 's/^ *\([0-9]*\) .*/\1/')
	errors=${errors:-0}
	p95=$(sed -n "$((start + (95 * n + 99) / 100))p" "$tmp/tenant-ms.tsv" | cut -f 2)
	start=$((start + n))
	row=$(grep "^$tenant$tab" "$tenants" | tail -n 1)
	row=${row:-$default}
	plan=$(printf '%s\n' "$row" | cut -f 2)
	budget=$(printf '%s\n' "$row" | cut -f 3)
	if [ $((100 * errors)) -ge "$n" ] || [ "$p95" -gt "$budget" ]; then
		printf '%s\t%s\t%s\t%s\t%s\t%s\t%s\n' $((errors * 1000000000000 / n)) "$p95" "$tenant" "$plan" "$n" \
			"$errors" "$budget" >> "$tmp/over.tsv"
	fi
done < "$tmp/tenant-counts"
if [ -s "$tmp/over.tsv" ]; then
	printf '%-20s %-10s %9s %6s %6s %7s %7s\n' tenant plan requests 5xx rate p95 budget
	sort -t "$tab" -k1,1nr -k2,2nr -k3,3 "$tmp/over.tsv" > "$tmp/over-sorted.tsv"
	while IFS="$tab" read -r key p95 tenant plan n errors budget; do
		tenths=$(( (2000 * errors + n) / (2 * n) ))
		printf '%-20s %-10s %9d %6d %3d.%d%% %7d %7d\n' "$tenant" "$plan" "$n" "$errors" $((tenths / 10)) \
			$((tenths % 10)) "$p95" "$budget"
	done < "$tmp/over-sorted.tsv"
else
	echo none
fi
