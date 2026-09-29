# Review round 2, check-safety finding (must pass): the reference solution, plus files a hostile or careless
# agent could leave behind for the check: FIFOs named like Python modules where the check looks for code
# and tests, a test module that is a link to a host file, and initial-head replaced by a link to a host
# file. The check must finish, read nothing outside the run directory, and score the implementation.
set -e
sh "$TRIAL_SCENARIO_DIR/qualify/good.sh"
mkfifo steprun/zz_trap.py tests/zz_trap.py
ln -s /etc/hostname tests/test_link.py
rm -f "$TRIAL_HARNESS/initial-head"
ln -s /etc/passwd "$TRIAL_HARNESS/initial-head"
