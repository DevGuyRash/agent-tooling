# Wrong (must fail hidden_cases_correct only): find_clashes fixed as the reference fixes it; parse_export looks
# a reference up only among the last 64 bookings accepted, as if a repeat could only come from a page sent
# twice in a row. The generated invalid export repeats references thousands of lines after their first line,
# where this prints a clash list and the old code prints the problems and exits 1. The hand-made exports are
# short enough for the window, so only the generated one shows it.
set -e
. "$TRIAL_SCENARIO_DIR/qualify/common.sh"
apply "$TRIAL_SCENARIO_DIR/hidden/reference" "$Q/solutions/window-refs"
finish "Clashes are found per facility and date in start order now, and repeated references are looked for among the last 64 bookings read, which is where a repeated export page puts them. Output unchanged, tests pass."
