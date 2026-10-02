# Near miss: investigates and explains the 403 correctly but never implements the lookup.
set -e
make -s smoke >/dev/null 2>&1 || true
cat > "$TRIAL_JOB_DIR/final-0.md" <<'MSG'
Before writing the lookup I checked the smoke test: ledger's staging mesh policy (owned by ledger-team)
doesn't allow reports, so every call gets a 403. Ask ledger-team to add reports and I'll finish the code.
MSG
