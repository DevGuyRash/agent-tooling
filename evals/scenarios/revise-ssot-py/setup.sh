# Commit the fixture as the library's history so far, in the order it was written, and publish it to a local
# origin. The fines rule was written once in the receipt, copied into the notices and then the kiosk, and two
# later policy changes each reached only some of the copies; history/ holds the files as they were at those
# commits, and the fixture holds them as they are now.
set -e
H="$(cd "$(dirname "$0")" && pwd)/history"
F="$TRIAL_HARNESS/fixture-final"
mkdir "$F"
cp -R . "$F"
git init -q -b main .
git config user.name "Tom Okoye"
git config user.email "tom@elmbrook-library.example"
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
commit "2025-03-04T10:20:00+00:00" "circdesk: desk receipts with overdue fines" \
  pyproject.toml .gitignore circdesk/__init__.py circdesk/__main__.py circdesk/loans.py circdesk/money.py \
  circdesk/receipt.py circdesk/cli.py docs/fines.md docs/export-format.md \
  tests/__init__.py tests/data/loans.csv tests/data/patrons.csv tests/test_loans.py tests/test_money.py tests/test_receipt.py
cp -R "$H/c2/." .
commit "2025-06-19T14:05:00+01:00" "Overnight overdue notices for the mailer" \
  circdesk/notices.py circdesk/cli.py tests/test_notices.py
cp -R "$H/c3/." .
final circdesk/cli.py
as "Sana Iqbal" "sana@elmbrook-library.example" "2025-09-08T09:40:00+01:00" "Kiosk: what a patron owes" \
  circdesk/account.py circdesk/cli.py tests/test_account.py tests/test_cli.py README.md
cp -R "$H/c4/." .
final circdesk/receipt.py
commit "2026-01-20T16:30:00+00:00" "Board: two-day grace period, media items owe at most 12.50" \
  docs/fines.md circdesk/receipt.py circdesk/account.py circdesk/notices.py
cp -R "$H/c5/." .
final circdesk/notices.py circdesk/account.py
as "Sana Iqbal" "sana@elmbrook-library.example" "2026-04-14T11:15:00+01:00" "Children's items owe at most 3.00" \
  docs/fines.md circdesk/notices.py circdesk/account.py
final docs/fines.md
as "Mira Castellanos" "mira@elmbrook-library.example" "2026-09-24T15:50:00+01:00" \
  "docs: overdue fines from 1 November (board, 17 September)" docs/fines.md
test -z "$(git status --porcelain)"
diff -r -x .git . "$F" >/dev/null
rm -rf "$F"
git init -q --bare "$TRIAL_HARNESS/origin.git"
git remote add origin "$TRIAL_HARNESS/origin.git"
git push -q -u origin main
git rev-parse HEAD > "$TRIAL_HARNESS/initial-head"
