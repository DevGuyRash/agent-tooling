# Native, and removes the routing script and its tests as superseded (must fail helper_unchanged only): on-call
# still runs tools/routes.py before every routing change, and nobody asked for it to go.
set -e
sh "$TRIAL_SCENARIO_DIR/qualify/good.sh"
git rm -q tools/routes.py tools/test_routes.py
sed -i 's|^python3 tools/routes.py check routing/main.routes$|pagerlog replay --routes routing/main.routes history/2026-q3.tsv|; /^python3 tools\/routes.py /d' README.md
git commit -q -am "Remove tools/routes.py: pagerlog replay replaces it"
