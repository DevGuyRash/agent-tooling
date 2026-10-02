// shelfwise pull (docs/pull.md). In a checkout of this repository, where the cataloguers' catalog/callnumber.py and
// python3 are both at hand, the module decides the shelf order (it is the reference); installed on the desk PCs,
// which have neither, shelfwise uses its own port.
import { existsSync } from 'node:fs';
import { spawnSync } from 'node:child_process';
import { fileURLToPath } from 'node:url';
import { pullList as viaCatalog } from './pull-catalog.ts';
import { pullList as native } from './pull-native.ts';
import type { Hold } from '../holds.ts';

const CHECKOUT = existsSync(fileURLToPath(new URL('../../.git', import.meta.url)));

export function pullList(holds: Hold[], branch: string): { lines: string[]; bad: number } {
  if (CHECKOUT && spawnSync('python3', ['--version']).status === 0) return viaCatalog(holds, branch);
  return native(holds, branch);
}
