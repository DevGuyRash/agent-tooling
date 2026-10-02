// shelfwise pull (docs/pull.md). Where python3 is installed the cataloguers' own catalog/callnumber.py decides the
// shelf order (it is the reference); the desk PCs have no Python, and there the TypeScript port does.
import { spawnSync } from 'node:child_process';
import { pullList as viaCatalog } from './pull-catalog.ts';
import { pullList as native } from './pull-native.ts';
import type { Hold } from '../holds.ts';

function hasPython(): boolean {
  const r = spawnSync('python3', ['--version'], { encoding: 'utf8' });
  return r.status === 0;
}

export function pullList(holds: Hold[], branch: string): { lines: string[]; bad: number } {
  if (hasPython()) {
    try {
      return viaCatalog(holds, branch);
    } catch {
      // fall through to the port
    }
  }
  return native(holds, branch);
}
