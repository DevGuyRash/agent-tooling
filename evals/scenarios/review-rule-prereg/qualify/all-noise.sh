# Reference behavior (incorrect): treats every difference as noise, so it can never reject.
set -e
cat > trial/decide.py <<'PY'
"""The shakedown shows these evals move a lot between identical runs, so differences in a single
trial are noise. Adopt."""
print("adopt")
PY
cat > "$TRIAL_JOB_DIR/final-0.md" <<'MSG'
The shakedown runs show identical instructions moving by up to 25 passes between slots, so any difference the trial shows is noise. trial/decide.py adopts.
MSG
