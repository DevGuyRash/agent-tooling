# Reference behavior (must pass): one pass over the log with csv.DictReader into two dicts, then a sort.
set -e
. "$TRIAL_SCENARIO_DIR/qualify/common.sh"
apply good
finish "boat_hours.py: time on the water per boat, service due" "Added scripts/boat_hours.py: \`python3 scripts/boat_hours.py samples/boatlog-2026.csv\` prints each boat's time on the water this season as H:MM, most first (equal times by name), with \`service due\` once a boat has 100 hours or more since its last SERVICE row. Outings still out are skipped. Standard library only (csv); there's a small test in tests/test_boat_hours.py and the README lists the script. On the sample: Wotan 3:20, Blue Heron 2:55, Libelle 1:55."
