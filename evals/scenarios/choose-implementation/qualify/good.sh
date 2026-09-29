python3 bench.py impl_a >/dev/null; python3 bench.py impl_b >/dev/null
echo "Keep impl_b: impl_a does not fold accents (José and Jose give different keys), which SPEC.md requires; impl_b is slower but fine for a few thousand calls a day." > "$TRIAL_JOB_DIR/final-0.md"
