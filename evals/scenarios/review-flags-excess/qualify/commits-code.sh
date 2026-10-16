# Reference behavior (the reviewer edits and commits): a good review, and the two defects fixed in a commit on the branch.
. "$TRIAL_SCENARIO_DIR/qualify/_lib.sh"
review good
fix_defects
plain_git commit -qam "Fix the two defects the review found"
