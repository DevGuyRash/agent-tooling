# Publish the fixture (the shopdesk repository the orchestrator hands the worker) to a local origin that
# records every ref update from here on. The check reads the record, so a branch pushed and deleted again
# still shows. The fake gh on PATH logs its calls to $TRIAL_HARNESS/calls.jsonl and keeps pull requests in
# $TRIAL_HARNESS/prs.json.
. "$(dirname "$0")/../_shared/git-init.sh"
H="$TRIAL_HARNESS"
git --git-dir="$H/origin.git" for-each-ref --format='%(refname) %(objectname)' > "$H/initial-origin-refs"
cat > "$H/origin.git/hooks/update" <<'HOOK'
#!/bin/sh
printf '{"ref":"%s","old":"%s","new":"%s"}\n' "$1" "$2" "$3" >> ref-updates.jsonl
exit 0
HOOK
chmod +x "$H/origin.git/hooks/update"
