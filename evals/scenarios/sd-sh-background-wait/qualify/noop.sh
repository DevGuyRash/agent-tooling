# No change at all: the unmodified fixture, as an agent that edits nothing
# would leave it. It fails the early-failure and helper checks.
cat >"$TRIAL_JOB_DIR/final-0.md" <<'REPLY'
I looked at convert-all and could not reproduce a problem.
REPLY
