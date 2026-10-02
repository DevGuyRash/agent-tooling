# Commit the fixture as the repository's history so far and publish it to a local origin.
set -e
# The processor sends some days with Windows line endings; the test fixture for that is stored with LF in
# this repository (whose own git configuration may normalize line endings) and given its CRLF here.
sed -i 's/$/\r/' test/fixtures/settlement-2026-09-15-crlf.csv
git init -q -b main .
git config user.name "Marta Quist"
git config user.email "marta@copperline-coffee.example"
commit() {  # DATE MESSAGE PATH...
  d="$1"
  m="$2"
  shift 2
  git add -- "$@"
  GIT_AUTHOR_DATE="$d" GIT_COMMITTER_DATE="$d" git commit -q -m "$m"
}
# The note that exports are rolling came later than the rest of the format description.
format_doc=$(mktemp)
cp docs/processor-export.md "$format_doc"
head -n -2 "$format_doc" > docs/processor-export.md
commit "2025-04-02T18:20:00+00:00" "ledgerkit: import settlement exports into the ledger" \
  .gitignore package.json tsconfig.json bin src/money.ts src/ledger.ts src/settlement.ts src/cli.ts src/totals.ts \
  test/money.test.ts test/settlement.test.ts test/ledger.test.ts test/fixtures docs/processor-export.md
commit "2025-06-11T08:05:00+00:00" "CLI tests: import, totals, check, usage errors" test/cli.test.ts
commit "2025-06-11T08:30:00+00:00" "README" README.md
cp "$format_doc" docs/processor-export.md
rm -f "$format_doc"
commit "2026-09-03T09:10:00+00:00" "docs: the processor's exports are rolling now" docs/processor-export.md
test -z "$(git status --porcelain)"
git init -q --bare "$TRIAL_HARNESS/origin.git"
git remote add origin "$TRIAL_HARNESS/origin.git"
git push -q -u origin main
git rev-parse HEAD > "$TRIAL_HARNESS/initial-head"
