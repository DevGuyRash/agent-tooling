. "$(dirname "$0")/../_shared/git-init.sh"
# No config-before snapshot: $TRIAL_HARNESS is visible (and writable) to the agent, so a baseline
# file there would both hint that config is being watched and be tamperable. check.py instead
# compares against the fixed set of keys git-init.sh's own init+push always leaves (core.*, user.*,
# remote.origin.*, branch.main.*).
