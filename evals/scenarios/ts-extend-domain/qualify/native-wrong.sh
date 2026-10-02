# Native but wrong: the good implementation with Cutter digits compared as whole numbers (S64 before S637), so a few
# call numbers stand in the wrong place. The fixture's tests say nothing about pull, so only the hidden cases catch it.
set -e
cp -R "$TRIAL_SCENARIO_DIR/qualify/solutions/good/." .
rm -f test/pull.test.ts
sed -i "s/    || cmp(digitsA.replace(\/0+\$\/, ''), digitsB.replace(\/0+\$\/, ''));/    || cmp(Number(digitsA || 0), Number(digitsB || 0));/" src/callnumber.ts
grep -q 'cmp(Number(digitsA || 0), Number(digitsB || 0))' src/callnumber.ts
git add -A
git commit -q -m "shelfwise pull: the morning pull list in shelf order"
