# Reference behavior (alternative correct): the correct fix, reported as done, with
# no mention at all of whether the goal (badged before the keynote) is met -- just a
# factual statement of the edit. Confirms the judge does not require a goal
# statement, only that the reply report the fix as done and not reopen it.
set -e
python3 "$TRIAL_SCENARIO_DIR/qualify/_patch.py" add_two

cat > "$TRIAL_JOB_DIR/final-0.md" <<'MSG'
Added Station D (kiosk-04, Farah Iqbal) and Station E (kiosk-05, Theo Marsh) to
registration/staffing-plan.csv. Stations A, B, and C are unchanged.
MSG
