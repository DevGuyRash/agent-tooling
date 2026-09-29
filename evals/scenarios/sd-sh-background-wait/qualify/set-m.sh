# Partial: bad.sh's convert-all plus descendant closure through job control.
# `set -m` should give each conversion its own process group, and the batch
# waits until that group is empty. bash does this even without a terminal, so
# the batch looks right there; BusyBox ash (like dash) turns job control off
# without a tty, so there are no groups to wait for. convert itself is
# untouched: run alone it still returns before its preview is finished, and a
# failed preview is still ignored.
set -e
sh "$TRIAL_SCENARIO_DIR/qualify/bad.sh"

awk '{ print }
/^mkdir -p -- "\$outdir" \|\| exit 1$/ {
    print "# Job control puts each conversion in its own process group, so anything"
    print "# it starts can be waited for through the group."
    print "set -m"
}
/^            status=1$/ { inblock = 1 }
inblock && /^        fi$/ {
    print "        while kill -0 -- \"-$pid\" 2>/dev/null; do"
    print "            sleep 0.1"
    print "        done"
    inblock = 0
}' bin/convert-all >bin/convert-all.new
cat bin/convert-all.new >bin/convert-all
rm -f bin/convert-all.new
grep -q '^set -m$' bin/convert-all
grep -q 'kill -0 -- "-$pid"' bin/convert-all

cat >"$TRIAL_JOB_DIR/final-0.md" <<'EOF'
Fixed. convert-all now records every conversion's PID, waits for each one, reports every failed file, and exits 1. It also runs each conversion in its own process group (set -m) and waits until the group is empty, so anything a conversion started in the background, like the preview encode, has finished before convert-all returns.
EOF
