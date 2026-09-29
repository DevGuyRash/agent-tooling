#!/bin/sh
# Run every tests/test_*.sh and report whether they all passed.
cd "$(dirname -- "$0")" || exit 1

status=0
for t in test_*.sh; do
    echo "# $t"
    sh "$t" || status=1
done

if [ "$status" -eq 0 ]; then
    echo "all tests passed"
else
    echo "some tests FAILED"
fi
exit "$status"
