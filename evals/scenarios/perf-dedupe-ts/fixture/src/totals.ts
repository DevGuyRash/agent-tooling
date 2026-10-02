// Daily totals per store, for the finance team's morning report.

import { formatCents } from './money.ts';
import type { LedgerRow } from './ledger.ts';

export interface DayTotal {
  date: string;
  store: string;
  sales: number;
  refunds: number;
  netCents: number;
}

/** Totals per (date, store), ordered by date then store; `from`/`to` are inclusive YYYY-MM-DD bounds. */
export function dailyTotals(rows: Iterable<LedgerRow>, from?: string, to?: string): DayTotal[] {
  const totals = new Map<string, DayTotal>();
  for (const row of rows) {
    const date = row.ts.slice(0, 10);
    if ((from && date < from) || (to && date > to)) continue;
    const key = `${date} ${row.store}`;
    let t = totals.get(key);
    if (!t) {
      t = { date, store: row.store, sales: 0, refunds: 0, netCents: 0 };
      totals.set(key, t);
    }
    if (row.amountCents < 0) t.refunds++;
    else t.sales++;
    t.netCents += row.amountCents;
  }
  return [...totals.values()].sort((a, b) => (a.date === b.date ? a.store.localeCompare(b.store) : a.date.localeCompare(b.date)));
}

export function formatTotals(totals: DayTotal[]): string {
  const lines = ['date        store  sales  refunds         net'];
  for (const t of totals) {
    lines.push(
      `${t.date}  ${t.store.padEnd(5)}  ${String(t.sales).padStart(5)}  ${String(t.refunds).padStart(7)}  ${formatCents(t.netCents).padStart(10)}`,
    );
  }
  return lines.join('\n') + '\n';
}
