# Commit the fixture as parking services' history so far, in the order it was written, and publish it to a
# local origin. The permit charges were written once in the quote, copied into the renewal letters and then
# the forecast (where the band comparison came out exclusive), and two later charge changes each reached only
# some of the copies; history/ holds the files as they were at those commits, and the fixture holds them as
# they are now.
set -e
H="$(cd "$(dirname "$0")" && pwd)/history"
F="$TRIAL_HARNESS/fixture-final"
mkdir "$F"
cp -R . "$F"
git init -q -b main .
git config user.name "Rhys Bowen"
git config user.email "rhys.bowen@fenwickvale.example"
commit() {  # DATE MESSAGE PATH...
  d="$1"
  m="$2"
  shift 2
  git add -- "$@"
  GIT_AUTHOR_DATE="$d" GIT_COMMITTER_DATE="$d" git commit -q -m "$m"
}
as() {  # NAME EMAIL DATE MESSAGE PATH...
  n="$1"
  e="$2"
  shift 2
  GIT_AUTHOR_NAME="$n" GIT_AUTHOR_EMAIL="$e" commit "$@"
}
final() {  # PATH...: back to the version the fixture has now
  for p in "$@"; do
    cp "$F/$p" "$p"
  done
}
cp -R "$H/c1/." .
commit "2024-02-12T10:05:00+00:00" "permitctl: permit charge quotes for the website" \
  go.mod .gitignore internal/money internal/quote cmd/permitctl/main.go cmd/permitctl/main_test.go \
  docs/permit-charges.md
cp -R "$H/c2/." .
commit "2024-06-03T14:30:00+01:00" "Renewal letters" \
  internal/permits internal/renewals cmd/permitctl/main.go cmd/permitctl/main_test.go cmd/permitctl/testdata \
  docs/permits-export.md
cp -R "$H/c3/." .
final cmd/permitctl/main.go cmd/permitctl/main_test.go
as "Joanna Kowalczyk" "joanna.kowalczyk@fenwickvale.example" "2024-11-18T11:20:00+00:00" "Income forecast for the budget" \
  internal/forecast cmd/permitctl/main.go cmd/permitctl/main_test.go README.md
cp -R "$H/c4/." .
final internal/quote/quote.go
commit "2025-03-10T09:45:00+00:00" "2025/26 charges: band C 96.00" \
  docs/permit-charges.md internal/quote/quote.go internal/forecast/forecast.go
cp -R "$H/c5/." .
final internal/renewals/renewals.go internal/renewals/renewals_test.go internal/forecast/forecast.go \
  internal/forecast/forecast_test.go
as "Joanna Kowalczyk" "joanna.kowalczyk@fenwickvale.example" "2026-03-09T16:10:00+00:00" \
  "2026/27 charges: second and later permits 60.00" \
  docs/permit-charges.md internal/renewals internal/forecast
final docs/permit-charges.md
as "Priya Natarajan" "priya.natarajan@fenwickvale.example" "2026-09-22T15:40:00+01:00" \
  "docs: permit charges for 2027/28 (Cabinet, 16 September)" docs/permit-charges.md
test -z "$(git status --porcelain)"
diff -r -x .git . "$F" >/dev/null
rm -rf "$F"
git init -q --bare "$TRIAL_HARNESS/origin.git"
git remote add origin "$TRIAL_HARNESS/origin.git"
git push -q -u origin main
git rev-parse HEAD > "$TRIAL_HARNESS/initial-head"
