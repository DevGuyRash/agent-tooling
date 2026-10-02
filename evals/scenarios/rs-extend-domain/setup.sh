# Commit the fixture as the repository's history so far, in the order the team wrote it, and publish it to a
# local origin. The routing files start as they were during the third quarter (the routing that decided the
# receivers in history/2026-q3.tsv) and change to today's in September. The manifests are stored as
# Cargo.toml.in so that this repository's CI, which builds every Cargo.toml it finds, does not treat the
# fixture as a workspace.
set -e
for m in Cargo.toml crates/history/Cargo.toml crates/table/Cargo.toml crates/pagerlog/Cargo.toml; do
  mv "$m.in" "$m"
done
git init -q -b main .
git config user.name "Jun Park"
git config user.email "jun@kittiwake.example"
commit() {  # DATE AUTHOR MESSAGE PATH...
  d="$1"
  a="$2"
  m="$3"
  shift 3
  git add -- "$@"
  GIT_AUTHOR_DATE="$d" GIT_COMMITTER_DATE="$d" git commit -q --author "$a" -m "$m"
}
TOMAS="Tomás Ferreira <tomas@kittiwake.example>"
mkdir -p "$TRIAL_HARNESS/setup"
cp -R routing "$TRIAL_HARNESS/setup/routing"
rm -r routing/teams
cat > routing/main.routes <<'ROUTES'
include "receivers.routes"
route {
  receiver platform-oncall
  route {
    match team = payments
    receiver payments-oncall
    route {
      match severity = info
      receiver payments-tickets
    }
    route {
      match env !~ prod*
      receiver payments-tickets
    }
  }
  route {
    match team = storage
    receiver storage-oncall
  }
  route {
    match severity = info
    receiver platform-tickets
  }
  route {
    match severity != critical
    during sat,sun 00:00-24:00
    receiver platform-weekend
  }
}
ROUTES
commit "2025-11-04T10:12:00+00:00" "$TOMAS" "routing: the paging service's receivers and routes" routing docs/routing.md
commit "2025-11-06T15:40:00+00:00" "$TOMAS" "tools/routes.py: check routing files and try alerts against them" tools
commit "2026-03-10T09:05:00+00:00" "Jun Park <jun@kittiwake.example>" "history: read the paging service's exports" \
  Cargo.toml Cargo.lock .cargo .gitignore crates/history docs/history.md
commit "2026-03-17T16:20:00+00:00" "Jun Park <jun@kittiwake.example>" "pagerlog: check, receivers, and top" \
  crates/table crates/pagerlog
rm -r routing
cp -R "$TRIAL_HARNESS/setup/routing" routing
rm -r "$TRIAL_HARNESS/setup"
commit "2026-09-24T11:30:00+00:00" "$TOMAS" "routing: DBA route, staging load tests, search team, team files" routing
commit "2026-09-25T10:00:00+00:00" "Jun Park <jun@kittiwake.example>" "README: layout, pagerlog, changing routing" README.md
commit "2026-10-01T08:10:00+00:00" "Jun Park <jun@kittiwake.example>" "history: 2026-Q3 export" history
commit "2026-10-01T09:30:00+00:00" "Priya Raman <priya@kittiwake.example>" \
  "docs: what pagerlog replay should print, for the routing review" docs/replay.md
test -z "$(git status --porcelain)"
git init -q --bare "$TRIAL_HARNESS/origin.git"
git remote add origin "$TRIAL_HARNESS/origin.git"
git push -q -u origin main
git rev-parse HEAD > "$TRIAL_HARNESS/initial-head"
