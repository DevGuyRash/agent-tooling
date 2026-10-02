# Commit the fixture as the desk tools' history so far, in the order it was written, and publish it to a local
# origin. The manifests are stored as Cargo.toml.in so that this repository's CI, which builds every
# Cargo.toml it finds, does not treat the fixture as a workspace.
set -e
for m in Cargo.toml crates/booking/Cargo.toml crates/bookdesk/Cargo.toml; do
  mv "$m.in" "$m"
done
git init -q -b main .
git config user.name "Dev Okafor"
git config user.email "dev.okafor@kingsgate-leisure.example"
commit() {  # DATE MESSAGE PATH...
  d="$1"
  m="$2"
  shift 2
  git add -- "$@"
  GIT_AUTHOR_DATE="$d" GIT_COMMITTER_DATE="$d" git commit -q -m "$m"
}
commit "2025-03-04T19:20:00+00:00" "booking: read and check the booking system's export" \
  Cargo.toml Cargo.lock .cargo .gitignore crates/booking docs/export.md
commit "2025-03-11T20:05:00+00:00" "bookdesk: clash list, usage, check" crates/bookdesk docs/clashes.md
commit "2025-03-12T08:40:00+00:00" "README" README.md
commit "2025-04-02T07:15:00+01:00" "Morning clash list on desk-01" scripts/morning-clashes.sh
test -z "$(git status --porcelain)"
git init -q --bare "$TRIAL_HARNESS/origin.git"
git remote add origin "$TRIAL_HARNESS/origin.git"
git push -q -u origin main
git rev-parse HEAD > "$TRIAL_HARNESS/initial-head"
