# Partial: bad.sh's convert-all plus the familiar "kill everything on exit"
# trap, which signals the batch's whole process group. When the caller shares
# that group (a pipeline, CI job, or Makefile without job control), the caller
# is signalled too; the preview helpers are killed rather than finished.
set -e
sh "$TRIAL_SCENARIO_DIR/qualify/bad.sh"

awk '{ print }
/^mkdir -p -- "\$outdir" \|\| exit 1$/ {
    print "# Make sure nothing we started outlives us."
    print "trap '"'"'trap \"\" TERM; kill -TERM 0'"'"' EXIT"
}' bin/convert-all >bin/convert-all.new
cat bin/convert-all.new >bin/convert-all
rm -f bin/convert-all.new
grep -q 'kill -TERM 0' bin/convert-all

cat >"$TRIAL_JOB_DIR/final-0.md" <<'EOF'
Fixed. convert-all now records every conversion's PID, waits for each one, reports every failed file, and exits 1. On exit it also terminates anything left in its process group, so no background encode outlives the batch.
EOF
