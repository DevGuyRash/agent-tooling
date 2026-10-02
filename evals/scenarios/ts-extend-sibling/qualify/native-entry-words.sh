# Native, with the timesheet reader keeping each note's words on the Entry (words: string[]), which invoice uses
# for +nobill, and a test for the new field. Must pass: the checks do not pin the Entry's exact fields.
set -e
sh "$TRIAL_SCENARIO_DIR/qualify/native.sh"
cp -R "$TRIAL_SCENARIO_DIR/qualify/solutions/entry-words/." .
cat >> test/timesheet.test.ts <<'TS'

test('the words of a note', () => {
  const [a, b] = parseTimesheet('2026-03-02  1h  acme/site  kickoff\tcall\n2026-03-03  1h  acme/site\n', 'w.txt');
  assert.deepEqual(a.words, ['kickoff', 'call']);
  assert.deepEqual(b.words, []);
});
TS
git add -A
git commit -q -m "timesheet: keep the words of each note"
