// shelfwise pull (docs/pull.md). Call numbers are read and ordered by catalog/callnumber.py, the cataloguers'
// module, so the desk and the catalog never disagree about the scheme.
import { spawnSync } from 'node:child_process';
import { fileURLToPath } from 'node:url';
import type { Hold } from '../holds.ts';

const CATALOG = fileURLToPath(new URL('../../catalog', import.meta.url));
const BRIDGE = `
import json, sys
sys.path.insert(0, sys.argv[1])
from callnumber import CallNumberError, parse
out = []
for text in json.load(sys.stdin):
    try:
        cn = parse(text)
        out.append({"text": str(cn), "key": cn.sort_key(), "section": cn.section()})
    except CallNumberError as exc:
        out.append({"error": str(exc)})
print(json.dumps(out))
`;

type Key = unknown;
interface Read { text?: string; key?: Key; section?: string; error?: string }

function compareKeys(a: Key, b: Key): number {
  if (Array.isArray(a) && Array.isArray(b)) {
    for (let i = 0; i < Math.min(a.length, b.length); i++) {
      const c = compareKeys(a[i], b[i]);
      if (c) return c;
    }
    return a.length - b.length;
  }
  return (a as number | string) < (b as number | string) ? -1 : (a as number | string) > (b as number | string) ? 1 : 0;
}

function readCallNumbers(texts: string[]): Read[] {
  const r = spawnSync('python3', ['-c', BRIDGE, CATALOG], { input: JSON.stringify(texts), encoding: 'utf8' });
  if (r.status !== 0) throw new Error(`catalog/callnumber.py failed: ${r.error?.message ?? r.stderr}`);
  return JSON.parse(r.stdout) as Read[];
}

export function pullList(holds: Hold[], branch: string): { lines: string[]; bad: number } {
  const waiting = holds.filter((h) => h.branch === branch && h.status === 'waiting');
  const read = waiting.length ? readCallNumbers(waiting.map((h) => h.callNumber)) : [];
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
