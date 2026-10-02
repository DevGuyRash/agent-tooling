#!/bin/sh
# The daily edge report (docs/daily-report.md). The report itself is scripts/daily_report.py; this wrapper keeps
# the path cron runs.
exec python3 "$(dirname "$0")/daily_report.py" "$@"
