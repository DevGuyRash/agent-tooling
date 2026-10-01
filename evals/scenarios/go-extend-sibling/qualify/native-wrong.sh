# Native but wrong: weeks keyed by calendar year and ISO week number, so the days of an ISO week that falls
# across New Year (2025-12-29 to 2026-01-04, 2020-12-28 to 2021-01-03) split into two weeks. Fails the
# hidden cases in both roots.
set -e
sh "$TRIAL_SCENARIO_DIR/qualify/native.sh"
sed -i 's/\t\ty, w := t.ISOWeek()/\t\t_, w := t.ISOWeek()/; s/return fmt.Sprintf("%04d-W%02d", y, w)/return fmt.Sprintf("%04d-W%02d", t.Year(), w)/' \
	internal/prune/prune.go
grep -q 't.Year(), w)' internal/prune/prune.go
git commit -q -am "prune: simpler week key"
