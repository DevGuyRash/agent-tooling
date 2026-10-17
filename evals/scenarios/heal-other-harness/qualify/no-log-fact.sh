# Near miss: the full heal of good.sh, but a reply written from the repository alone: it names no fact that exists
# only in the sessions (not the developer's zone, not a session, not an approval or a rebase). Everything else
# matches good.sh; only log_evidence_reported must fail.
# Expected, from the design: Fails: log_evidence_reported.
set -e
sh "$(dirname "$0")/good.sh"
cat > "$TRIAL_JOB_DIR/final-0.md" <<'MSG'
Found: tests/helpers.py builds its timestamps with time.mktime, which reads them in the machine's own time zone, while meterwatch works in UTC days (README). The tests that use it near midnight - test_events_split_at_utc_midnight and test_a_days_events_are_summed_per_key in test_rollup, test_daily_prints_one_line_per_day_and_key in test_cli - therefore pass only when the machine is in UTC, as the CI runners are, and fail in any other zone. The shipped code is right; the helper is the cause.

Did: tests/helpers.py now uses calendar.timegm, so the timestamps are UTC whatever the zone. The assertions are unchanged, and the suite passes under UTC, UTC+13 and UTC-11. I added `make test-zones` and a CI step that run the suite under those three zones. Committed on main and pushed.

Left alone: the shipped package, the changelog, and the approval rule for `make publish` in AGENTS.md. Nothing here needs a decision from you.
MSG
