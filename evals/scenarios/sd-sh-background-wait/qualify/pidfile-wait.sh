# Partial: bad.sh's convert-all, extended to settle the preview helper from the
# batch. convert writes the helper's PID to a file and the batch calls wait on
# it, but that PID is not a child of the batch's shell: wait returns 127 at
# once, so the helper still outlives its job and its status is never known.
set -e
sh "$TRIAL_SCENARIO_DIR/qualify/bad.sh"

old='    -codec:a libmp3lame -b:a 128k "$preview" &'
grep -qxF "$old" bin/convert
awk -v old="$old" '{ print } $0 == old { print "echo \"$!\" >\"$outdir/.$name.preview.pid\"" }' \
    bin/convert >bin/convert.new
cat bin/convert.new >bin/convert
rm -f bin/convert.new

awk '{ print }
/^            status=1$/ { inblock = 1 }
inblock && /^        fi$/ {
    print "        eval \"src=\\$src_$pid\""
    print "        name=${src##*/}"
    print "        pidfile=$outdir/.${name%.wav}.preview.pid"
    print "        if [ -f \"$pidfile\" ]; then"
    print "            # the preview encode convert started in the background"
    print "            wait \"$(cat \"$pidfile\")\" 2>/dev/null || :"
    print "            rm -f -- \"$pidfile\""
    print "        fi"
    inblock = 0
}' bin/convert-all >bin/convert-all.new
cat bin/convert-all.new >bin/convert-all
rm -f bin/convert-all.new
grep -q 'preview.pid' bin/convert-all
grep -q 'preview.pid' bin/convert

cat >"$TRIAL_JOB_DIR/final-0.md" <<'EOF'
Fixed. convert-all now records every conversion's PID, waits for each one, reports every failed file, and exits 1. convert records the PID of the preview encode it starts in the background, and convert-all waits for that too before it returns, so nothing is still being written when it exits.
EOF
