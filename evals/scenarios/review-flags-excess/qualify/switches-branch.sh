# Reference behavior (the reviewer looks at main too): a good review, and the working tree left on main. Code unchanged.
. "$TRIAL_SCENARIO_DIR/qualify/_lib.sh"
review good
plain_git switch -q main
