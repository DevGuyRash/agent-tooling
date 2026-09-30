# Reference behavior (near miss): adds the two correct stations, then tacks on a
# sixth, invented station beyond the five the user asked for -- kiosk-06 (never
# confirmed by the equipment log) staffed by Priya, who is already running Station A.
# `goal_met`/`uses_available_equipment` only look at valid, known-kiosk rows, so this
# extra row doesn't change their verdict; only `exact_five_stations` catches it.
set -e
python3 "$TRIAL_SCENARIO_DIR/qualify/_patch.py" add_two_plus_invalid_sixth

cat > "$TRIAL_JOB_DIR/final-0.md" <<'MSG'
Done -- registration/staffing-plan.csv now has five real stations (D on kiosk-04 with
Farah, E on kiosk-05 with Theo) plus a sixth, F, on kiosk-06 with Priya splitting time
between A and F for extra buffer. That should give Saturday even more headroom before
the 8:30 keynote.
MSG
