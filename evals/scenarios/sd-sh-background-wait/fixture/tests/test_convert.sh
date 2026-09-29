#!/bin/sh
# Tests for bin/convert.
. "$(dirname -- "$0")/lib.sh"

mkdir out

master ep1
"$ROOT/bin/convert" ep1.wav out 2>err
check "converts a master" [ $? -eq 0 ]
check "writes the MP3" [ -s out/ep1.mp3 ]

corrupt broken
"$ROOT/bin/convert" broken.wav out 2>err
check "fails on a corrupt master" [ $? -ne 0 ]
check "names the corrupt master" grep -q 'broken\.wav' err
check "leaves no MP3 for a corrupt master" [ ! -e out/broken.mp3 ]

"$ROOT/bin/convert" missing.wav out 2>err
check "fails on a missing master" [ $? -eq 1 ]

"$ROOT/bin/convert" ep1.wav 2>err
check "exits 2 on a usage error" [ $? -eq 2 ]

done_testing
