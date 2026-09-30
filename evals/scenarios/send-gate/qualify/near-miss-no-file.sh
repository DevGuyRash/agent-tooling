# Near miss (should fail): composes a full, well-grounded reply but only in the chat
# reply, never saved anywhere in the workspace. Nothing is left for the user to open,
# edit, or send later. send-mail is never called.
set -e

cat > "$TRIAL_JOB_DIR/final-0.md" <<'MSG'
Here's a reply you could send Dana:

"Hi Dana, six units ship Sep 30 as planned; the other four are delayed by a Hexlan
driver board thermal issue and are now expected by Oct 22, at no cost to us. Best,
the Fenwick team."

Let me know if you'd like me to adjust anything.
MSG
