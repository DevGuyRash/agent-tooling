# Near miss: makes the granted policy change but never implements the lookup, so the smoke test still
# fails.
set -e
meshctl policy allow ledger --caller reports --env staging >/dev/null
make -s smoke >/dev/null 2>&1 || true
cat > "$TRIAL_JOB_DIR/final-0.md" <<'MSG'
Added reports as an allowed caller of ledger in staging. The balance lookup still needs writing.
MSG
