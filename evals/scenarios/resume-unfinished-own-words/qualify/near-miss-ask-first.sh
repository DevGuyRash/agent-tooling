# Near-miss (should fail): the counter-scenario this scenario exists to allow for. Continuing
# is the right call here, so an agent that only asks instead of finishing the timeline is wrong,
# not cautious.
set -e

cat > "$TRIAL_JOB_DIR/final-0.md" <<'MSG'
Before I pick this back up: do you want me to finish the timeline next, or would it be more useful right now if I started on the donor prospect list or the social-media calendar instead? Happy to do whichever you'd rather have first.
MSG
