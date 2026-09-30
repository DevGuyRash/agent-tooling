. "$(dirname "$0")/../../scenarios/_shared/git-init.sh"

# Baselines for residue checks that need to know what setup itself left, not what the agent added.
git config --local --list > "$TRIAL_HARNESS/config-before"
ls .git > "$TRIAL_HARNESS/git-toplevel-before"
