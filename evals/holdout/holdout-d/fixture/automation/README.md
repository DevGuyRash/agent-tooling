# Automation

The ops server can run commands on a recurring schedule.

- `jobsctl schedule "<cron-expression>" -- <command...>` registers a recurring job that keeps running on that schedule until it's removed.
- `jobsctl run -- <command...>` runs a command once, right now, and exits.
- `jobsctl list` shows what's currently scheduled.

Nothing is currently scheduled.

## Notes

- 2026-09-23 (ops assistant): placed this week's flour/eggs/cocoa restock by hand again. Keep meaning
  to wire this up with `jobsctl schedule` so it just happens every Monday instead of someone asking --
  haven't gotten to it yet, just noting it here for next time.
