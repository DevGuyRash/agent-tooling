// hours invoice: the month-end script, which already knows the rate card and the billing rules, prints the
// invoice; hours passes the command line through.

import { spawnSync } from 'node:child_process';
import { fileURLToPath } from 'node:url';
import type { Result } from '../result.ts';

const SCRIPT = fileURLToPath(new URL('../../scripts/invoice.py', import.meta.url));

export function invoice(args: string[]): Result {
  const r = spawnSync('python3', [SCRIPT, '--table', ...args], { encoding: 'utf8' });
  if (r.error) return { code: 1, stdout: '', stderr: `hours invoice: ${r.error.message}\n` };
  return { code: r.status ?? 1, stdout: r.stdout, stderr: r.stderr };
}
