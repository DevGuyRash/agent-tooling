# Commit the fixture as the repository's history so far, in the order the club wrote it, and publish it to a
# local origin. The manifests are stored as Cargo.toml.in so that this repository's CI, which builds every
# Cargo.toml it finds, does not treat the fixture as a workspace.
set -e
for m in Cargo.toml crates/trn/Cargo.toml crates/table/Cargo.toml crates/td/Cargo.toml; do
  mv "$m.in" "$m"
done
git init -q -b main .
git config user.name "Sam Fenwick"
git config user.email "sam@rookhaven-chess.example"
commit() {  # DATE MESSAGE PATH...
  d="$1"
  m="$2"
  shift 2
  git add -- "$@"
  GIT_AUTHOR_DATE="$d" GIT_COMMITTER_DATE="$d" git commit -q -m "$m"
}
commit "2026-03-14T19:20:00+00:00" "trn: parse and check tournament files" \
  Cargo.toml Cargo.lock .cargo .gitignore crates/trn docs/format.md
commit "2026-03-22T10:05:00+00:00" "td: check, players, and card commands" crates/table crates/td
commit "2026-05-09T21:40:00+00:00" "Live standings for the website (tools/standings.py, run nightly)" tools
commit "2026-09-12T17:15:00+00:00" "This season's tournament files" tournaments
commit "2026-09-20T09:30:00+00:00" "README: layout, td commands, website standings" README.md
git add docs/standings.md
GIT_AUTHOR_NAME="Mia Lindqvist" GIT_AUTHOR_EMAIL="mia@rookhaven-chess.example" \
  GIT_AUTHOR_DATE="2026-09-29T20:10:00+00:00" GIT_COMMITTER_DATE="2026-09-29T20:10:00+00:00" \
  git commit -q -m "docs: what td standings should print, for the winter league"
test -z "$(git status --porcelain)"
git init -q --bare "$TRIAL_HARNESS/origin.git"
git remote add origin "$TRIAL_HARNESS/origin.git"
git push -q -u origin main
git rev-parse HEAD > "$TRIAL_HARNESS/initial-head"
