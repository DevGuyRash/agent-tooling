#!/bin/sh
# logreport - summarize a web server access log in the combined format.
#
# usage: logreport.sh [-n N] [-s STATUS] [FILE...]
#   -n N       how many entries to list under "top paths" and "top clients" (default 5)
#   -s STATUS  only count requests whose status code starts with STATUS (5, 40, 404, ...)
#
# Reads standard input when no FILE is given.
# Exit status: 0 report printed, 1 a FILE cannot be read, 2 bad usage.
set -eu

usage() {
	echo "usage: logreport.sh [-n N] [-s STATUS] [FILE...]" >&2
	exit 2
}

top=5
want=
while getopts n:s: opt; do
	case $opt in
	n) top=$OPTARG ;;
	s) want=$OPTARG ;;
	*) usage ;;
	esac
done
shift $((OPTIND - 1))

case $top in
'' | *[!0-9]*)
	echo "logreport: -n wants a whole number, got '$top'" >&2
	exit 2
	;;
esac
case $want in
*[!0-9]*)
	echo "logreport: -s wants digits, got '$want'" >&2
	exit 2
	;;
esac

for f in "$@"; do
	if [ ! -r "$f" ] || [ -d "$f" ]; then
		echo "logreport: cannot read $f" >&2
		exit 1
	fi
done

export LC_ALL=C
work=$(mktemp -d)
trap 'rm -rf "$work"' EXIT

# One line per counted request: client, path (query string dropped), status, bytes.
# A line counts when field 9 is a status code and field 10 is a byte count or "-";
# anything else (truncated lines, requests nginx could not parse) is skipped.
cat -- "$@" | awk -v want="$want" '
	NF >= 10 && $9 ~ /^[1-5][0-9][0-9]$/ && ($10 ~ /^[0-9]+$/ || $10 == "-") {
		if (want != "" && index($9, want) != 1) next
		path = $7
		sub(/\?.*/, "", path)
		print $1, path, $9, ($10 == "-" ? 0 : $10)
	}' >"$work/requests"

total=$(wc -l <"$work/requests")
total=$((total + 0))
echo "requests: $total"
[ "$total" -gt 0 ] || exit 0

clients=$(cut -d' ' -f1 "$work/requests" | sort -u | wc -l)
echo "clients: $((clients + 0))"

# Status classes that occurred, lowest first.
awk '{ n[substr($3, 1, 1)]++ }
	END {
		line = "status:"
		for (c = 1; c <= 5; c++) if (c in n) line = line " " c "xx=" n[c]
		print line
	}' "$work/requests"

awk '{ b += $4 }
	END {
		if (b >= 1048576) printf "bytes: %.1f MiB\n", b / 1048576
		else if (b >= 1024) printf "bytes: %.1f KiB\n", b / 1024
		else printf "bytes: %d B\n", b
	}' "$work/requests"

# Most requests first; equal counts in byte order of the name.
top_of() {
	cut -d' ' -f"$1" "$work/requests" | sort | uniq -c | sort -k1,1nr -k2,2 | head -n "$top" |
		awk '{ printf "%6d  %s\n", $1, $2 }'
}

echo "top paths:"
top_of 2
echo "top clients:"
top_of 1
