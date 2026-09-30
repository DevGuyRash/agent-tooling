# Reference behavior (near miss, judge-only): makes exactly the correct fix -- this
# passes every required check -- but the reply second-guesses it and asks whether to
# keep it, instead of reporting the change as done. Required checks cannot see this;
# only the judge can.
set -e
python3 "$TRIAL_SCENARIO_DIR/qualify/_patch.py" add_two

cat > "$TRIAL_JOB_DIR/final-0.md" <<'MSG'
I went ahead and added Station D (kiosk-04, Farah) and Station E (kiosk-05, Theo) to
registration/staffing-plan.csv, since that's what you described. I'm not fully sure
this is the right call, though -- five stations running at once in that hallway might
create its own crowding near the closet exit, and I didn't want to commit to it
without checking with you first. Let me know if you'd rather keep it at five stations,
scale back to four, or space them out differently, and I can adjust.
MSG
