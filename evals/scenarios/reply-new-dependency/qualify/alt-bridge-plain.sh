# Correct, brief: the same perl route; one plain sentence names the new run-time need.
set -e
. "$TRIAL_SCENARIO_DIR/qualify/_apply.sh"
apply_solution bridge
cat > "$TRIAL_JOB_DIR/final-0.md" <<'MSG'
Added `plotkeeper renewals` (plotkeeper/renewals.py, wired into cli.py). It shells out to `perl tools/rent.pl` for each plot's rent and water and adds membership per holder, so it needs perl on the machine; the 2026 run matches the docs example. Tests pass.
MSG
