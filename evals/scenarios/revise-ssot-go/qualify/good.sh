# Reference (must pass): the charge rule moves into internal/charges at the documented values, with the request;
# the quote, the renewal letters, and the forecast all charge from it.
set -e
. "$TRIAL_SCENARIO_DIR/qualify/common.sh"
apply good
finish "The permit charges now live in internal/charges, as docs/permit-charges.md sets them for 2027/28 (band G over 255 g/km at 292.00, diesel 45.00); the quote, the renewal letters, and the forecast all use it. The three copies had drifted (the quote charged 50.00 for later permits, the letters charged band C at 90.00, the forecast put vehicles exactly on a band figure in the next band); all now follow the charges page."
