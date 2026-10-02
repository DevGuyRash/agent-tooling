// Which transactions of an export the ledger already holds.
//
// The export has no transaction ID, so a transaction is its whole ledger line, and identical lines can be
// separate transactions (two taps of the same card at the same till within a minute). The ledger's copies
// of a line account for the export's first copies of it; the rest are new.

import { formatLedgerLine } from './ledger.ts';
import type { LedgerRow } from './ledger.ts';

/** Indexes into `incoming` of the rows the ledger does not already hold, ascending. */
export function unmatchedIndexes(ledger: LedgerRow[], incoming: LedgerRow[]): number[] {
  const held = ledger.map(formatLedgerLine).sort();
  const lines = incoming.map(formatLedgerLine);
  // Stable order: by line, then by position in the export, so earlier copies are matched first.
  const order = lines.map((_, i) => i).sort((a, b) => (lines[a] < lines[b] ? -1 : lines[a] > lines[b] ? 1 : a - b));
  const fresh: number[] = [];
  let h = 0;
  for (const i of order) {
    while (h < held.length && held[h] < lines[i]) h++;
    if (h < held.length && held[h] === lines[i]) h++;
    else fresh.push(i);
  }
  return fresh.sort((a, b) => a - b);
}
