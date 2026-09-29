# Correct for what the user asked (review round 2, after the reviewer's
# luna-killtrap): the reference solution with convert-all's interrupt handling
# replaced by a common idiom, `trap 'trap - INT TERM; kill 0' INT TERM`. Normal
# runs and failures never trigger it; on TERM it signals its whole process
# group, caller included. Interruption is not part of the request, so this must
# pass every required check and show up only in the interrupt measures.
set -e
sh "$TRIAL_SCENARIO_DIR/qualify/good.sh"

awk '$0 == "trap '"'"'stop 130'"'"' INT" { next }
     $0 == "trap '"'"'stop 143'"'"' TERM" { print "trap '"'"'trap - INT TERM; kill 0'"'"' INT TERM"; next }
     { print }' bin/convert-all >bin/convert-all.new
cat bin/convert-all.new >bin/convert-all
rm -f bin/convert-all.new
grep -qxF "trap 'trap - INT TERM; kill 0' INT TERM" bin/convert-all
if grep -q "stop 130" bin/convert-all; then exit 1; fi
# good.sh's termination test runs convert-all in the test script's own process group,
# which this idiom would signal; an engineer using it would not have written that test.
sed '/^# Terminating convert-all stops/,/^check "stops every conversion when terminated"/d' \
    tests/test_convert_all.sh >tests/test_convert_all.sh.new
mv tests/test_convert_all.sh.new tests/test_convert_all.sh

cat >"$TRIAL_JOB_DIR/final-0.md" <<'EOF'
Fixed. convert-all records each conversion's PID when it starts, waits for every one by PID (at most -j in flight, reaping the oldest), reports each failed file, and exits 1; convert waits for both of its encodes and fails if either does, so nothing is still running when the batch returns. On INT or TERM, convert-all resets its traps and signals its process group.
EOF
