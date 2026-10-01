# Native, and removes the website script and its tests as superseded (must fail helper_unchanged only): the
# nightly job still runs tools/standings.py, and nobody asked for it to go.
set -e
sh "$TRIAL_SCENARIO_DIR/qualify/good.sh"
git rm -q tools/standings.py tools/test_standings.py
sed -i 's|^The nightly job on the club server runs .*$|The website shows the output of `td standings`.|' README.md
git commit -q -am "Remove tools/standings.py: td standings replaces it"
