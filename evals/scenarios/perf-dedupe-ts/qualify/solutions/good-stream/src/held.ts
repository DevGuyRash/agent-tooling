// The ledger lines that tonight's export could overlap, counted, without loading the whole ledger.
//
// An export only covers its own few days, so only ledger lines from its first day on can match. The
// ledger is read in chunks and those lines are counted as they are (import writes them in canonical form),
// so the 2.4M-line history never becomes millions of objects.

import { closeSync, existsSync, openSync, readSync } from 'node:fs';
import { LEDGER_HEADER, LedgerError, formatLedgerLine } from './ledger.ts';
import type { LedgerRow } from './ledger.ts';

const CHUNK = 1 << 20;

/** How many times each ledger line dated `since` (YYYY-MM-DD) or later appears. */
export function heldSince(path: string, since: string): Map<string, number> {
  const held = new Map<string, number>();
  if (!existsSync(path)) return held;
  const fd = openSync(path, 'r');
  try {
    const buf = Buffer.alloc(CHUNK);
    let rest = '';
    let first = true;
    for (;;) {
      const n = readSync(fd, buf, 0, CHUNK, null);
      const text = rest + buf.toString('utf8', 0, n);
      const lines = text.split('\n');
      rest = n === 0 ? '' : (lines.pop() ?? '');
      for (const line of lines) {
        if (first) {
          if (line !== LEDGER_HEADER) throw new LedgerError(`${path}:1: not a ledger (expected "${LEDGER_HEADER}")`);
          first = false;
        } else if (line !== '' && line.slice(0, 10) >= since) {
          held.set(line, (held.get(line) ?? 0) + 1);
        }
      }
      if (n === 0) break;
    }
  } finally {
    closeSync(fd);
  }
  return held;
}

/** The export's rows that are not in the ledger yet; repeated identical rows are counted, not collapsed. */
export function notYetImported(ledgerPath: string, rows: LedgerRow[]): LedgerRow[] {
  if (rows.length === 0) return [];
  let since = rows[0].ts;
  for (const r of rows) if (r.ts < since) since = r.ts;
  const held = heldSince(ledgerPath, since.slice(0, 10));
  return rows.filter((row) => {
    const line = formatLedgerLine(row);
    const n = held.get(line) ?? 0;
    if (n === 0) return true;
    held.set(line, n - 1);
    return false;
  });
}
