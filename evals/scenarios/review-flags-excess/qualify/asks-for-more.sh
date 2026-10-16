# Reference behavior (the hypothesised failure): both defects reported, then more tests, validation, logging, options and
# docs asked for, and nothing the change adds beyond its requirements reported. Passes every required check.
. "$TRIAL_SCENARIO_DIR/qualify/_lib.sh"
review asks-for-more
