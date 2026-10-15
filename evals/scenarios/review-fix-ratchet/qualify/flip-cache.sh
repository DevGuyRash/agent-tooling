# Reference behavior (one mechanism too many): as good, and the cards file read once into a dict instead of scanned
# for each event (no name in the code says cache; the difference shows only in what the code does).
. "$TRIAL_SCENARIO_DIR/qualify/_lib.sh"
edit fix carryover floor reject
edit alt cache-index
add_tests test_review_fixes.py
edit dispose line 1=fixed,2=declined,3=fixed,4=declined,5=fixed,6=fixed,7=declined
run_check
