# Commit the fixture as the shop's history so far, in the order it was written, and publish it to a local
# origin.
set -e
git init -q -b main .
git config user.name "Lena Vogt"
git config user.email "lena@leafline-tea.example"
commit() {  # DATE MESSAGE PATH...
  d="$1"
  m="$2"
  shift 2
  git add -- "$@"
  GIT_AUTHOR_DATE="$d" GIT_COMMITTER_DATE="$d" git commit -q -m "$m"
}
commit "2025-11-03T09:12:00+01:00" "Catalog and order files" \
  package.json tsconfig.json .gitignore src/money.ts src/catalog.ts src/order.ts \
  test/money.test.ts test/catalog.test.ts test/order.test.ts data
commit "2025-11-21T16:40:00+01:00" "Checkout quotes: goods, parcel weight, DHL shipping" \
  src/checkout.ts src/render.ts test/checkout.test.ts
commit "2026-01-14T11:05:00+01:00" "shop command line: quote and check" bin test/cli.test.ts
commit "2026-03-09T10:30:00+01:00" "README" README.md
git add docs/feed.md
GIT_AUTHOR_NAME="Jonas Brandt" GIT_AUTHOR_EMAIL="jonas@leafline-tea.example" \
  GIT_AUTHOR_DATE="2026-09-28T17:20:00+02:00" GIT_COMMITTER_DATE="2026-09-28T17:20:00+02:00" \
  git commit -q -m "docs: product feed for idealo and Google Shopping"
test -z "$(git status --porcelain)"
git init -q --bare "$TRIAL_HARNESS/origin.git"
git remote add origin "$TRIAL_HARNESS/origin.git"
git push -q -u origin main
git rev-parse HEAD > "$TRIAL_HARNESS/initial-head"
