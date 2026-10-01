#!/bin/sh
# Run every case in tests/cases against logreport.
#
#   tests/run.sh                       # tests scripts/logreport.sh
#   LOGREPORT=./other tests/run.sh     # tests another build of it
#
# A case is NAME.args (the arguments, split on spaces; file names are relative to tests/data),
# NAME.expected (the exact standard output), and optionally NAME.stdin (fed to standard input)
# and NAME.status (the expected exit status, 0 when absent).
cd "$(dirname "$0")/.." || exit 1
prog=${LOGREPORT:-scripts/logreport.sh}
case $prog in /*) ;; *) prog=$PWD/$prog ;; esac

fail=0
for args in tests/cases/*.args; do
	name=${args%.args}
	case=$(basename "$name")
	stdin=/dev/null
	[ -f "$name.stdin" ] && stdin=$PWD/$name.stdin
	want_status=0
	[ -f "$name.status" ] && want_status=$(cat "$name.status")
	# shellcheck disable=SC2046 # word splitting of the argument line is intended
	set -- $(cat "$args")
	got=$(cd tests/data && "$prog" "$@" <"$stdin" 2>/dev/null)
	status=$?
	if [ "$status" -ne "$want_status" ]; then
		echo "FAIL $case: exit status $status, want $want_status"
		fail=1
	elif [ "$got" != "$(cat "$name.expected")" ]; then
		echo "FAIL $case: output differs"
		printf '%s\n' "$got" | diff -u "$name.expected" - | sed 's/^/    /'
		fail=1
	else
		echo "ok   $case"
	fi
done
exit $fail
