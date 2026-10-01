here="$(dirname "$0")"
. "$here/_dates.sh"

# The fixture's inbox and status files carry sentinel 2026 dates; shift them (and the inbox
# filename, which encodes the same date) to land on "today" before committing them -- see
# _dates.sh for why.
mv "inbox/2026-09-28-dana-chen.md" "inbox/$EMAIL_ISO-dana-chen.md"
rewrite_story_dates "inbox/$EMAIL_ISO-dana-chen.md"
rewrite_story_dates "status/foundry-pilot-status.md"

. "$here/../_shared/git-init.sh"
