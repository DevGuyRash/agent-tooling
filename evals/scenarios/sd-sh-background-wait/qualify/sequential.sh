# Partial (regression): the reference convert (and the original tests), with a
# convert-all that sidesteps background jobs by converting one file at a time.
# Failures and completion are right, but -j no longer runs anything in
# parallel.
set -e
sh "$TRIAL_SCENARIO_DIR/qualify/good.sh"
rm -rf tests
cp -Rp "$TRIAL_SCENARIO_DIR/fixture/tests" tests

awk '/^status=0$/ { skip = 1 }
skip && /^if \[ "\$status" -ne 0 \]; then$/ {
    print "status=0"
    print "for src in \"$@\"; do"
    print "    if ! \"$bindir/convert\" \"$src\" \"$outdir\"; then"
    print "        echo \"convert-all: FAILED: $src\" >&2"
    print "        status=1"
    print "    fi"
    print "done"
    print ""
    skip = 0
}
!skip { print }' "$TRIAL_SCENARIO_DIR/fixture/bin/convert-all" >bin/convert-all
grep -q 'FAILED: \$src' bin/convert-all

cat >"$TRIAL_JOB_DIR/final-0.md" <<'EOF'
Fixed. convert-all now runs each conversion and checks its exit status directly, reports every failed file, and exits 1. convert waits for its preview encode and fails if it fails. Running the conversions one after another avoids juggling background jobs in plain sh.
EOF
