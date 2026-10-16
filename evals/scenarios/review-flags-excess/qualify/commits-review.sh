# Reference behavior (the reviewer commits only the review): a good review, committed on the branch. Code unchanged.
. "$TRIAL_SCENARIO_DIR/qualify/_lib.sh"
review good
plain_git add REVIEW.md
plain_git commit -qm "Add the review of the overdue branch"
