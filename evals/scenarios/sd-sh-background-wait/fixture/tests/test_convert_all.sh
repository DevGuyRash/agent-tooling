#!/bin/sh
# Tests for bin/convert-all.
. "$(dirname -- "$0")/lib.sh"

master ep1
master ep2
master ep3

"$ROOT/bin/convert-all" -o out ep1.wav ep2.wav ep3.wav >log 2>&1
check "converts a batch" [ $? -eq 0 ]
for n in ep1 ep2 ep3; do
    check "writes out/$n.mp3" [ -s "out/$n.mp3" ]
done
check "reports how many files it converted" grep -q 'converted 3 file' log

"$ROOT/bin/convert-all" -j 1 -o serial ep1.wav ep2.wav ep3.wav >log 2>&1
check "converts one at a time with -j 1" [ $? -eq 0 ]
for n in ep1 ep2 ep3; do
    check "writes serial/$n.mp3" [ -s "serial/$n.mp3" ]
done

corrupt bad
"$ROOT/bin/convert-all" -o partial ep1.wav bad.wav >log 2>&1
check "exits 1 when a conversion fails" [ $? -eq 1 ]
check "still converts the other files" [ -s partial/ep1.mp3 ]

"$ROOT/bin/convert-all" -j 0 ep1.wav >log 2>&1
check "rejects -j 0" [ $? -eq 2 ]
"$ROOT/bin/convert-all" >log 2>&1
check "needs at least one file" [ $? -eq 2 ]

done_testing
