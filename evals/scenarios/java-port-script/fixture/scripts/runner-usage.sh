#!/bin/sh
# runner-usage: CI runner minutes per team from the CI job export, against the monthly budgets.
#
#   scripts/runner-usage.sh [-b BUDGETS] [-m YYYY-MM] [-p POOL]... [-n N] [FILE...]
#
# Reads the job export (CSV, no quoting: job_id,team,pool,date,seconds,status; a first line starting with
# job_id is the header) from the FILEs, or standard input when there are none. Lines that do not fit that
# shape are skipped and counted on standard error. Each job bills its seconds rounded up to whole minutes,
# and at least one minute. -m keeps the jobs of one month, -p (repeatable) the jobs on the named pools,
# -n prints only the N teams with the most minutes (0, the default, prints every team). BUDGETS has one
# "team minutes" line per team, # comments, and an optional "* minutes" line for every team not listed.
#
# Exit status: 0, or 1 when any team is over its budget (shown or not), 2 for a usage error or a bad
# budgets line, 3 when an input or the budgets file cannot be read.
set -u
LC_ALL=C
export LC_ALL
prog=runner-usage

usage() {
	echo "usage: $prog [-b BUDGETS] [-m YYYY-MM] [-p POOL]... [-n N] [FILE...]" >&2
	exit 2
}

budgets='' month='' pools='' top=0
while getopts b:m:p:n: opt; do
	case $opt in
	b) budgets=$OPTARG ;;
	m)
		case $OPTARG in
		[0-9][0-9][0-9][0-9]-[01][0-9]) month=$OPTARG ;;
		*) echo "$prog: -m wants YYYY-MM, got '$OPTARG'" >&2; exit 2 ;;
		esac
		;;
	p)
		case $OPTARG in
		'' | *[!a-z0-9-]*) echo "$prog: bad pool name '$OPTARG'" >&2; exit 2 ;;
		esac
		pools="$pools $OPTARG"
		;;
	n)
		case $OPTARG in
		'' | *[!0-9]*) echo "$prog: -n wants a number, got '$OPTARG'" >&2; exit 2 ;;
		esac
		top=$OPTARG
		;;
	*) usage ;;
	esac
done
shift $((OPTIND - 1))

for f in ${budgets:+"$budgets"} "$@"; do
	if [ ! -f "$f" ] || [ ! -r "$f" ]; then
		echo "$prog: cannot read $f" >&2
		exit 3
	fi
done

tmp=$(mktemp) || exit 3
trap 'rm -f "$tmp"' EXIT HUP INT TERM

# Stage 1: one line per team (team, jobs, failed, minutes, budget or 0 for none).
awk -F, -v month="$month" -v pools="$pools" -v budgets="$budgets" -v prog="$prog" '
BEGIN {
	npools = split(pools, p, " ")
	for (i = 1; i <= npools; i++) want[p[i]] = 1
	if (budgets != "") {
		ln = 0
		while ((r = getline line < budgets) > 0) {
			ln++
			sub(/#.*/, "", line)
			n = split(line, w, " ")
			if (n == 0) continue
			if (n != 2 || w[2] !~ /^[0-9]+$/ || w[2] + 0 == 0) {
				printf "%s: %s line %d: expected \"team minutes\"\n", prog, budgets, ln > "/dev/stderr"
				bad = 1
				exit 2
			}
			budget[w[1]] = w[2] + 0
		}
	}
}
FNR == 1 && $1 == "job_id" { next }
NF != 6 || $2 !~ /^[a-z][a-z0-9-]*$/ || $3 == "" || $4 !~ /^[0-9][0-9][0-9][0-9]-[0-9][0-9]-[0-9][0-9]$/ ||
    $5 !~ /^[0-9]+$/ || ($6 != "success" && $6 != "failed" && $6 != "canceled") {
	skipped++
	next
}
month != "" && substr($4, 1, 7) != month { next }
npools > 0 && !($3 in want) { next }
{
	m = int(($5 + 59) / 60)
	if (m < 1) m = 1
	jobs[$2]++
	minutes[$2] += m
	if ($6 == "failed") failed[$2]++
}
END {
	if (bad) exit 2
	if (skipped) printf "%s: skipped %d malformed %s\n", prog, skipped, (skipped == 1 ? "line" : "lines") > "/dev/stderr"
	for (t in jobs) {
		b = (t in budget) ? budget[t] : (("*" in budget) ? budget["*"] : 0)
		printf "%s\t%d\t%d\t%d\t%d\n", t, jobs[t], failed[t] + 0, minutes[t], b
	}
}' "$@" >"$tmp" || exit $?

# Stage 2: most minutes first (ties by team name), the table, and the exit status.
tab=$(printf '\t')
sort -t "$tab" -k4,4nr -k1,1 "$tmp" | awk -F "$tab" -v top="$top" '
BEGIN { printf "%-16s %6s %7s %9s %7s %6s\n", "TEAM", "JOBS", "FAILED", "MINUTES", "BUDGET", "USED" }
{
	teams++
	tj += $2; tf += $3; tm += $4
	over = ($5 > 0 && $4 > $5)
	if (over) anyover = 1
	if (top > 0 && teams > top) next
	if ($5 > 0) { b = $5; u = int($4 * 100 / $5) "%" } else { b = "-"; u = "-" }
	printf "%-16.16s %6d %7d %9d %7s %6s%s\n", $1, $2, $3, $4, b, u, (over ? " !" : "")
}
END {
	if (top > 0 && teams > top) printf "... and %d more %s\n", teams - top, (teams - top == 1 ? "team" : "teams")
	printf "%-16s %6d %7d %9d\n", "TOTAL", tj, tf, tm
	exit anyover ? 1 : 0
}'
