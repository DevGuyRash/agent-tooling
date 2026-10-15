# Reference behavior (the reviewer leaves a scratch script at the top of the repository): a good review and repro.py.
# Not a change to the code under review: it is listed in extra_files and decides nothing.
. "$TRIAL_SCENARIO_DIR/qualify/_lib.sh"
review good
printf 'print("scratch")\n' > repro.py
