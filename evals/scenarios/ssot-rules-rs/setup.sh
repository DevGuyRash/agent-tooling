# Commit the fixture as the race office's history so far, in the order it was written, and publish it to a
# local origin. The manifests are stored as Cargo.toml.in so that this repository's CI, which builds every
# Cargo.toml it finds, does not treat the fixture as a workspace.
set -e
for m in Cargo.toml crates/race/Cargo.toml crates/results/Cargo.toml crates/startline/Cargo.toml; do
  mv "$m.in" "$m"
done
git init -q -b main .
git config user.name "Owen Pryce"
git config user.email "owen@ternpoint-sc.example"
commit() {  # DATE MESSAGE PATH...
  d="$1"
  m="$2"
  shift 2
  git add -- "$@"
  GIT_AUTHOR_DATE="$d" GIT_COMMITTER_DATE="$d" git commit -q -m "$m"
}
commit "2026-02-21T15:10:00+00:00" "race: race files, clock times, table layout" \
  Cargo.toml Cargo.lock .cargo .gitignore crates/race docs/race-file.md
commit "2026-03-07T11:45:00+00:00" "results: handicap results with the 2026 Portsmouth Numbers" crates/results
commit "2026-04-11T09:20:00+01:00" "startline: start sequence signal times" crates/startline
commit "2026-09-21T18:05:00+01:00" "Autumn series race files" races
commit "2026-09-22T20:30:00+01:00" "README" README.md
git add docs/pursuit.md docs/pursuit-example.race
GIT_AUTHOR_NAME="Priya Nair" GIT_AUTHOR_EMAIL="priya@ternpoint-sc.example" \
  GIT_AUTHOR_DATE="2026-09-29T21:15:00+01:00" GIT_COMMITTER_DATE="2026-09-29T21:15:00+01:00" \
  git commit -q -m "docs: pursuit start times for the winter series"
test -z "$(git status --porcelain)"
git init -q --bare "$TRIAL_HARNESS/origin.git"
git remote add origin "$TRIAL_HARNESS/origin.git"
git push -q -u origin main
git rev-parse HEAD > "$TRIAL_HARNESS/initial-head"
