# Reference behavior: write qualify/reviews/NAME.md as REVIEW.md, as a reviewer would, and change nothing else.
# Usage: sh review.sh NAME. What each review says, and so which checks it passes, is in qualify/README.md.
. "$TRIAL_SCENARIO_DIR/qualify/_lib.sh"
review "$1"
