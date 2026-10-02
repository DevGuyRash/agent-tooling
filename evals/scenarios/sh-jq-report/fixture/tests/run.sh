#!/bin/sh
# Run the daily report on each tests/cases/*.jsonl and compare it with the .expected file beside it.
set -eu
cd "$(dirname "$0")/.."
failed=0
for log in tests/cases/*.jsonl; do
	want=${log%.jsonl}.expected
	if sh scripts/daily-report.sh "$log" | cmp -s - "$want"; then
		echo "ok   $log"
	else
		echo "FAIL $log"
		failed=1
	fi
done
exit $failed
