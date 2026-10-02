// The card processor's nightly settlement export (docs/processor-export.md), turned into ledger rows.

import { parseAmount } from './money.ts';
import type { LedgerRow } from './ledger.ts';

export const EXPORT_HEADER = 'Date,Time,Store,Terminal,Card,Amount,Type';

const DATE = /^\d{4}-\d{2}-\d{2}$/;
const TIME = /^\d{2}:\d{2}$/;
const STORE = /^S\d{2}$/;

export interface ParsedExport {
  rows: LedgerRow[];
  errors: string[];
}

/** Parse a whole export. Every problem is reported (with file:line); rows are only meaningful without errors. */
export function parseSettlementExport(text: string, name: string): ParsedExport {
  const lines = text.split('\n').map((line) => (line.endsWith('\r') ? line.slice(0, -1) : line));
  const rows: LedgerRow[] = [];
  const errors: string[] = [];
  if (lines[0] !== EXPORT_HEADER) {
    return { rows, errors: [`${name}:1: not a settlement export (expected "${EXPORT_HEADER}")`] };
  }
  for (let i = 1; i < lines.length; i++) {
    if (lines[i].trim() === '') continue;
    const where = `${name}:${i + 1}`;
    try {
      rows.push(toLedgerRow(lines[i], where));
    } catch (e) {
      errors.push((e as Error).message);
    }
  }
  return { rows, errors };
}

function toLedgerRow(line: string, where: string): LedgerRow {
  const f = line.split(',').map((s) => s.trim());
  if (f.length !== 7) throw new Error(`${where}: expected 7 fields, found ${f.length}`);
  const [date, time, rawStore, terminal, card, amount, type] = f;
  const store = rawStore.toUpperCase();
  if (!DATE.test(date)) throw new Error(`${where}: bad date ${JSON.stringify(date)}`);
  if (!TIME.test(time)) throw new Error(`${where}: bad time ${JSON.stringify(time)}`);
  if (!STORE.test(store)) throw new Error(`${where}: bad store ${JSON.stringify(rawStore)}`);
  if (!/^[1-9]\d*$/.test(terminal)) throw new Error(`${where}: bad terminal ${JSON.stringify(terminal)}`);
  const last4 = card.replace(/[^0-9]/g, '').slice(-4);
  if (last4.length !== 4) throw new Error(`${where}: bad card ${JSON.stringify(card)}`);
  let cents: number;
  try {
    cents = parseAmount(amount);
  } catch {
    throw new Error(`${where}: bad amount ${JSON.stringify(amount)}`);
  }
  if (cents === 0) throw new Error(`${where}: zero amount`);
  if (type !== 'SALE' && type !== 'REFUND') throw new Error(`${where}: bad type ${JSON.stringify(type)}`);
  return {
    ts: `${date}T${time}`,
    store,
    terminal: Number(terminal),
    card: last4,
    amountCents: type === 'REFUND' ? -cents : cents,
  };
}
