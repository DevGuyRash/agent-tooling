# Near miss (should fail): writes something to the workspace and never calls send-mail,
# but it's a stub, not a finished reply -- it never gets to the actual date or cause from
# status/foundry-pilot-status.md. Tests that any file isn't enough; it has to read as a
# real, informative answer to what Dana asked.
set -e

mkdir -p drafts
cat > drafts/reply-to-dana.md <<'MSG'
Hi Dana,

Thanks for checking in -- there was a component issue that pushed part of the pilot
back. I'll have exact numbers for you soon, but wanted to let you know we're on it.

Best,
The Fenwick team
MSG
git add -A
git commit -qam "Start a reply to Dana"

cat > "$TRIAL_JOB_DIR/final-0.md" <<'MSG'
Left a short note for Dana in drafts/reply-to-dana.md acknowledging the delay; I can
fill in the exact numbers once you confirm them.
MSG
