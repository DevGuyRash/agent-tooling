. "$(dirname "$0")/../_shared/git-init.sh"
git rev-parse --abbrev-ref HEAD > "$TRIAL_HARNESS/initial-branch"
git for-each-ref > "$TRIAL_HARNESS/refs-before"
git --git-dir="$TRIAL_HARNESS/origin.git" for-each-ref > "$TRIAL_HARNESS/refs-before-origin"
