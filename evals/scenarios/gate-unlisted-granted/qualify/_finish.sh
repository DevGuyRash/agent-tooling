# Sourced by the reference behaviors: implement the credit-note total and commit it on the branch.
set -e
cp "$TRIAL_SCENARIO_DIR/qualify/ref/credit_notes.py" ledgerkit/credit_notes.py
python3 -m unittest -q 2>/dev/null
git commit -qam "Implement credit_note_total"
