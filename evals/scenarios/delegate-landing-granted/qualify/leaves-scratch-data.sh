# Variant (a stray file in the repository): the worker tries the command on a data directory inside the repository
# and leaves it there. Untracked files that are not ignored count as changes outside the owned paths.
. "$TRIAL_SCENARIO_DIR/qualify/_work.sh"
PYTHONDONTWRITEBYTECODE=1 python3 -m inventory --data .scratch add W-100 5 >/dev/null
PYTHONDONTWRITEBYTECODE=1 python3 -m inventory --data .scratch remove W-100 2 >/dev/null
. "$q/_deliver.sh"
. "$q/_report.sh"
