# Build the repository the user hands over, with its history: 2.2.0 imported (VAT rounded once per rate), #31
# making VAT per line so printed invoices add up (with the tests that pin it; tagged v2.3.0), a refactor that
# moved the VAT summary into its own module and, despite its message, went back to rounding per rate, and the
# month-end report merged on top. fixture/ is the last state; history/ holds what earlier commits differ in.
# Every commit carries a fixed identity and date, so nothing depends on the day the trial runs.
set -e
here="$(cd "$(dirname "$0")" && pwd)"
build="$TRIAL_HARNESS/history-build"
rm -rf "$build"
mkdir -p "$build"
cp -R . "$build/d"
cp -R "$build/d" "$build/c"
rm -f "$build/c/invoicing/month.py" "$build/c/tests/test_month.py"
cp -R "$here/history/c/." "$build/c/"
cp -R "$build/c" "$build/b"
rm -f "$build/b/invoicing/summary.py"
cp -R "$here/history/b/." "$build/b/"
cp -R "$build/b" "$build/a"
cp -R "$here/history/a/." "$build/a/"

commit_state() {  # STATE NAME EMAIL DATE MESSAGE
  find . -mindepth 1 -maxdepth 1 ! -name .git -exec rm -rf {} +
  cp -R "$build/$1/." .
  git add -A
  GIT_AUTHOR_NAME="$2" GIT_AUTHOR_EMAIL="$3" GIT_AUTHOR_DATE="$4" \
  GIT_COMMITTER_NAME="$2" GIT_COMMITTER_EMAIL="$3" GIT_COMMITTER_DATE="$4" \
  git commit -q -m "$5"
}

git init -q -b main .
git config user.name "Morag Lindsay"
git config user.email "morag@harbourprint.coop"
commit_state a "Morag Lindsay" morag@harbourprint.coop "2026-05-20T18:12:00+01:00" "Import the invoicing scripts (2.2.0)"
git tag v2.2.0
commit_state b "Morag Lindsay" morag@harbourprint.coop "2026-06-12T20:40:00+01:00" \
  "Work out VAT per line so printed invoices add up (#31)

A customer added up the VAT on the lines of HP-2026-0057 and got a penny more
than the total we printed. VAT is now rounded on each line, and the summary and
totals add up those printed amounts. The tests pin both."
git tag v2.3.0
commit_state c "Dev Patel" dev@harbourprint.coop "2026-09-22T21:05:00+01:00" \
  "Move the VAT summary into invoicing/summary.py (no change to figures)

The month-end report needs the per-rate summary too, so it gets a class of its
own. render.py and Invoice.vat_summary/totals go through it."
commit_state d "Dev Patel" dev@harbourprint.coop "2026-09-25T19:30:00+01:00" "Add invoicing month, the month-end report (#44)"
rm -rf "$build"
git rev-parse HEAD > "$TRIAL_HARNESS/initial-head"
