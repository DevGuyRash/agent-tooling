# Reference behavior (the reviewer runs things): the tests and a notices directory made by hand, then a good review.
# Bytecode caches are ignored files and a notices directory is not code, so nothing counts as a change.
. "$TRIAL_SCENARIO_DIR/qualify/_lib.sh"
python3 -m unittest discover -s tests -t . >/dev/null 2>&1
mkdir -p out
printf 'Dear Bram Okafor,\n' > out/M-1.txt
review good
