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

# Tenants over budget (docs/daily-report.md), in plain sh: the rows sorted by tenant and ms, then one loop.
printf '\nTenants over budget\n'
tab=$(printf '\t')
default_plan= default_budget=
while IFS="$tab" read -r t p b; do
	case $t in '#'*|'') continue ;; esac
	if [ "$t" = '*' ]; then default_plan=$p default_budget=$b; fi
done < "$tenants"
lookup() {
	found_plan=$default_plan found_budget=$default_budget
	while IFS="$tab" read -r t p b; do
		case $t in '#'*|'') continue ;; esac
		if [ "$t" = "$1" ]; then found_plan=$p found_budget=$b; fi
	done < "$tenants"
}
cut -f 1,2,5 "$tmp/requests.tsv" | while IFS="$tab" read -r status ms tenant; do
	[ "$tenant" = - ] && continue
	printf '%s\t%s\t%s\n' "$tenant" "$ms" "$status"
done | sort -t "$tab" -k1,1 -k2,2n > "$tmp/tenant-ms.tsv"
: > "$tmp/over.tsv"
emit() {
	rank=$(( (95 * n + 99) / 100 ))
	p95=$(sed -n "${rank}p" "$tmp/one-tenant")
	lookup "$cur"
	if [ $((100 * errors)) -ge "$n" ] || [ "$p95" -gt "$found_budget" ]; then
		# rate key: errors/n scaled to 12 digits so sort -n compares it exactly enough
		key=$(( errors * 1000000000000 / n ))
		printf '%s\t%s\t%s\t%s\t%s\t%s\t%s\n' "$key" "$p95" "$cur" "$found_plan" "$n" "$errors" "$found_budget" >> "$tmp/over.tsv"
	fi
}
cur= n=0 errors=0
: > "$tmp/one-tenant"
while IFS="$tab" read -r tenant ms status; do
	if [ "$tenant" != "$cur" ]; then
		if [ "$n" -gt 0 ]; then emit; fi
		cur=$tenant n=0 errors=0
		: > "$tmp/one-tenant"
	fi
	n=$((n + 1))
	if [ "$status" -ge 500 ] && [ "$status" -le 599 ]; then errors=$((errors + 1)); fi
	echo "$ms" >> "$tmp/one-tenant"
done < "$tmp/tenant-ms.tsv"
if [ "$n" -gt 0 ]; then emit; fi
if [ -s "$tmp/over.tsv" ]; then
	printf '%-20s %-10s %9s %6s %6s %7s %7s\n' tenant plan requests 5xx rate p95 budget
	sort -t "$tab" -k1,1nr -k2,2nr -k3,3 "$tmp/over.tsv" | while IFS="$tab" read -r key p95 t p n e b; do
		tenths=$(( (2000 * e + n) / (2 * n) ))
		printf '%-20s %-10s %9d %6d %3d.%d%% %7d %7d\n' "$t" "$p" "$n" "$e" $((tenths / 10)) $((tenths % 10)) "$p95" "$b"
	done
else
	echo none
fi
