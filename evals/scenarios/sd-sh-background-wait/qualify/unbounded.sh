# Partial (regression): the reference solution (with the original tests), but
# the rewritten convert-all starts every conversion at once and then waits for
# each by PID. Status and cleanup are right; -j no longer bounds anything.
set -e
sh "$TRIAL_SCENARIO_DIR/qualify/good.sh"
rm -rf tests
cp -Rp "$TRIAL_SCENARIO_DIR/fixture/tests" tests

grep -q '|| reap_oldest$' bin/convert-all
grep -v -e '|| reap_oldest$' -e '# At most \$jobs in flight' -e '# portable bound is to wait for the oldest' \
    bin/convert-all >bin/convert-all.new
cat bin/convert-all.new >bin/convert-all
rm -f bin/convert-all.new

cat >"$TRIAL_JOB_DIR/final-0.md" <<'EOF'
Fixed. convert-all now starts every conversion, records each PID as it starts, waits for every one by PID, reports each failed file, and exits 1. convert waits for its preview encode and fails if either encode fails. Both stop their children on TERM/INT/HUP.
EOF
