// The ledger: one line per card transaction, the whole chain's history, appended to by `ledgerkit import`.
//
//   ts,store,terminal,card,amount_cents
//   2026-09-14T07:42,S07,2,4821,450
//
// ts is the store's local time to the minute, card the last four digits, and amount_cents is negative for a
// refund. A line holds everything the processor tells us about a transaction.

import { appendFileSync, existsSync, readFileSync, writeFileSync } from 'node:fs';

export const LEDGER_HEADER = 'ts,store,terminal,card,amount_cents';

export interface LedgerRow {
  ts: string;
  store: string;
  terminal: number;
  card: string;
  amountCents: number;
}

const TS = /^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}$/;
const STORE = /^S\d{2}$/;
const CARD = /^\d{4}$/;
const INTEGER = /^-?\d+$/;

export class LedgerError extends Error {}

export function formatLedgerLine(row: LedgerRow): string {
  return `${row.ts},${row.store},${row.terminal},${row.card},${row.amountCents}`;
}

/** Parse one ledger line; `where` (file:line) goes into the error message. */
export function parseLedgerLine(line: string, where: string): LedgerRow {
  const f = line.split(',');
  if (f.length !== 5) throw new LedgerError(`${where}: expected 5 fields, found ${f.length}`);
  const [ts, store, terminal, card, amount] = f;
  if (!TS.test(ts)) throw new LedgerError(`${where}: bad timestamp ${JSON.stringify(ts)}`);
  if (!STORE.test(store)) throw new LedgerError(`${where}: bad store ${JSON.stringify(store)}`);
  if (!/^[1-9]\d*$/.test(terminal)) throw new LedgerError(`${where}: bad terminal ${JSON.stringify(terminal)}`);
  if (!CARD.test(card)) throw new LedgerError(`${where}: bad card ${JSON.stringify(card)}`);
  if (!INTEGER.test(amount) || amount === '0' || amount === '-0') {
    throw new LedgerError(`${where}: bad amount ${JSON.stringify(amount)}`);
  }
  return { ts, store, terminal: Number(terminal), card, amountCents: Number(amount) };
}

/** Every row of the ledger, in file order; an empty list when the file does not exist yet. */
export function readLedger(path: string): LedgerRow[] {
  if (!existsSync(path)) return [];
  const lines = readFileSync(path, 'utf8').split('\n');
  if (lines[0] !== LEDGER_HEADER) throw new LedgerError(`${path}:1: not a ledger (expected "${LEDGER_HEADER}")`);
  const rows: LedgerRow[] = [];
  for (let i = 1; i < lines.length; i++) {
    if (lines[i] === '') continue;
    rows.push(parseLedgerLine(lines[i], `${path}:${i + 1}`));
  }
  return rows;
}

/**
 * The rows of `incoming` that the ledger does not already hold, in their order. Identical lines can be
 * separate transactions, so this counts: a line the ledger holds n times accounts for its first n copies in
 * `incoming`, and any further copies are new.
 */
export function newTransactions(ledger: LedgerRow[], incoming: LedgerRow[]): LedgerRow[] {
  const held = new Map<string, number>();
  for (const row of ledger) {
    const line = formatLedgerLine(row);
    held.set(line, (held.get(line) ?? 0) + 1);
  }
  const fresh: LedgerRow[] = [];
  for (const row of incoming) {
    const line = formatLedgerLine(row);
    const left = held.get(line) ?? 0;
    if (left > 0) held.set(line, left - 1);
    else fresh.push(row);
  }
  return fresh;
}

/** Append rows to the ledger, creating it (with its header) if needed. */
export function appendToLedger(path: string, rows: LedgerRow[]): void {
  if (!existsSync(path)) writeFileSync(path, LEDGER_HEADER + '\n');
  if (rows.length === 0) return;
  appendFileSync(path, rows.map(formatLedgerLine).join('\n') + '\n');
}
