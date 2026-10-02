# Wrong (must fail failures_as_specified only): a TaskGroup whose ExceptionGroup is not unwrapped, so the
# server's except BookNotFound / except PageUnavailable no longer catch the failures (a 500 instead).
set -e
cp -R "$TRIAL_SCENARIO_DIR/qualify/solutions/wrong/." .
git add -A
git commit -q -m "Book page: ask the four backends at once"
