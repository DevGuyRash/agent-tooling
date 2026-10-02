# Reference behavior (must pass): the four lookups start together in a TaskGroup; a required lookup that
# fails raises at once, the group cancels the others (their connections close as they are cancelled), and the
# error is raised on its own, catalog's first. Adds tests for the overlap and the early 503.
set -e
cp -R "$TRIAL_SCENARIO_DIR/qualify/solutions/good/." .
git add -A
git commit -q -m "Book page: ask the four backends at once"
