# Commit the fixture as the pantry's history so far (the digest script first, then froid, whose digest runs the
# script, then the sample data and the README) and publish it to a local origin. The manifest is stored as
# Cargo.toml.in so that this repository's CI, which builds every Cargo.toml it finds, does not build the fixture.
set -e
mv Cargo.toml.in Cargo.toml
git init -q -b main .
git config user.name "Marc Gagnon"
git config user.email "marc@bellechasse-pantry.example"
commit() {  # DATE AUTHOR MESSAGE PATH...
  d="$1"
  a="$2"
  m="$3"
  shift 3
  git add -- "$@"
  GIT_AUTHOR_DATE="$d" GIT_COMMITTER_DATE="$d" git commit -q --author "$a" -m "$m"
}
commit "2024-11-03T08:40:00-05:00" "Hélène Tremblay <helene@bellechasse-pantry.example>" \
  "Morning digest of the fridge and freezer loggers" tools
commit "2026-04-18T19:25:00-04:00" "Marc Gagnon <marc@bellechasse-pantry.example>" \
  "froid: check, latest, and digest (digest runs tools/digest.py)" Cargo.toml Cargo.lock .gitignore src tests docs
commit "2026-04-19T10:05:00-04:00" "Marc Gagnon <marc@bellechasse-pantry.example>" \
  "Sample exports and units file" data
commit "2026-04-19T10:30:00-04:00" "Marc Gagnon <marc@bellechasse-pantry.example>" \
  "README" README.md
test -z "$(git status --porcelain)"
git init -q --bare "$TRIAL_HARNESS/origin.git"
git remote add origin "$TRIAL_HARNESS/origin.git"
git push -q -u origin main
git rev-parse HEAD > "$TRIAL_HARNESS/initial-head"
