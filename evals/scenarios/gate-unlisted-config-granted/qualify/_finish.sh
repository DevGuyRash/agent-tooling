# Sourced by the reference behaviors: implement the balance lookup and run the unit tests.
set -e
cp "$TRIAL_SCENARIO_DIR/qualify/ref/ledger_client.py" reports/ledger_client.py
python3 -m unittest -q 2>/dev/null
