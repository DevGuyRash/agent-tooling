here="$(dirname "$0")"
. "$here/_dates.sh"

# The fixture's email and run-of-show carry sentinel 2026 dates for the request and the launch;
# shift them to keep the launch a few days ahead of "today" before committing -- see _dates.sh.
rewrite_event_date request-email.md
rewrite_event_date run-of-show.md

. "$here/../../scenarios/_shared/git-init.sh"
git log -1 --format=%H > "$TRIAL_HARNESS/head-before"
