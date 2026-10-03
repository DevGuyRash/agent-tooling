# Sourced by the reference behaviors.
set -e
Q="$TRIAL_SCENARIO_DIR/qualify/solutions"
fix_code() { cp "$Q/fix/invoicing/summary.py" invoicing/summary.py; }
edit() { python3 "$TRIAL_SCENARIO_DIR/qualify/edit.py" "$@"; }
commit() { git add -A && git commit -qm "$1"; }
reply() { cat > "$TRIAL_JOB_DIR/final-0.md"; }
