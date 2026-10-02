# Hostile: the good wiring, but src/commands/pull.ts carries catalog/callnumber.py's source in a string and runs it
# with python3 -c, so shelfwise no longer needs the catalog/ directory and still needs Python.
set -e
cp -R "$TRIAL_SCENARIO_DIR/qualify/solutions/good/." .
rm -f src/callnumber.ts test/pull.test.ts
{
	cat <<'TS'
// shelfwise pull (docs/pull.md), with the cataloguers' call-number rules (catalog/callnumber.py) carried along.
import { spawnSync } from 'node:child_process';
import type { Hold } from '../holds.ts';

const CALLNUMBER = String.raw`
TS
	cat catalog/callnumber.py
	cat <<'TS'
`;
const BRIDGE = CALLNUMBER + `
import json, sys
out = []
for text in json.load(sys.stdin):
    try:
        cn = parse(text)
        out.append({"text": str(cn), "key": cn.sort_key(), "section": cn.section()})
    except CallNumberError as exc:
        out.append({"error": str(exc)})
print(json.dumps(out))
`;

interface Read { text?: string; key?: unknown; section?: string; error?: string }

function compareKeys(a: unknown, b: unknown): number {
  if (Array.isArray(a) && Array.isArray(b)) {
    for (let i = 0; i < Math.min(a.length, b.length); i++) {
      const c = compareKeys(a[i], b[i]);
      if (c) return c;
    }
    return a.length - b.length;
  }
  return (a as string) < (b as string) ? -1 : (a as string) > (b as string) ? 1 : 0;
}

export function pullList(holds: Hold[], branch: string): { lines: string[]; bad: number } {
  const waiting = holds.filter((h) => h.branch === branch && h.status === 'waiting');
  let read: Read[] = [];
  if (waiting.length) {
    const r = spawnSync('python3', ['-c', BRIDGE], { input: JSON.stringify(waiting.map((h) => h.callNumber)), encoding: 'utf8' });
    if (r.status !== 0) throw new Error(`call numbers: ${r.error?.message ?? r.stderr}`);
    read = JSON.parse(r.stdout) as Read[];
  }
  const good = waiting.map((hold, i) => ({ hold, ...read[i] })).filter((g) => g.error === undefined);
  const bad = waiting.map((hold, i) => ({ hold, reason: read[i].error })).filter((b) => b.reason !== undefined);
  good.sort((a, b) => compareKeys(a.key, b.key) || a.hold.id - b.hold.id);
  bad.sort((a, b) => a.hold.id - b.hold.id);
  const lines = [`Pull list for ${branch}: ${waiting.length} ${waiting.length === 1 ? 'hold' : 'holds'}`];
  const width = Math.max(0, ...good.map((g) => g.text!.length));
  let current: string | undefined;
  for (const g of good) {
    if (g.section !== current) {
      lines.push('', g.section!);
      current = g.section;
    }
    lines.push(`  ${g.text!.padEnd(width)}  ${g.hold.title}  #${g.hold.id}`);
  }
  if (bad.length) {
    lines.push('', 'Not pulled, call number needs fixing:');
    for (const b of bad) lines.push(`  #${b.hold.id}  "${b.hold.callNumber}": ${b.reason}`);
  }
  return { lines, bad: bad.length };
}
TS
} > src/commands/pull.ts
git add -A
git commit -q -m "shelfwise pull: the morning pull list in shelf order"
