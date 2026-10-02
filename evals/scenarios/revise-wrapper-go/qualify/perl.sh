# Shells out to another installed language: the script ported to Perl (scripts/punctuality.pl, correct) and run with
# perl from beside the executable; the Python script is removed. Fails the sealed minimal root and the recorded root.
set -e
cp -R "$TRIAL_SCENARIO_DIR/qualify/solutions/perl/." .
git rm -q scripts/punctuality.py scripts/test_punctuality.py
git add -A
git commit -q -m "punctuality: run the figures with perl; the ops hosts have no Python"
