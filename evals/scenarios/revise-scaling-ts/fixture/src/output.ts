// The two files a charge run writes (docs/fares.md, "What the run writes"), and reading charges back.

import type { Charge, Reason } from './fares.ts';
import type { Debit } from './debits.ts';

export const CHARGES_HEADER = 'ts,card,route,stop,fare_cents,charged_cents,reason';
export const DEBITS_HEADER = 'card,taps,charged_cents';

export function chargesCsv(charges: Charge[]): string {
  const lines = [CHARGES_HEADER];
  for (const { tap, charged, reason } of charges) {
    lines.push(`${tap.ts},${tap.card},${tap.route},${tap.stop},${tap.fare},${charged},${reason}`);
  }
  return lines.join('\n') + '\n';
}

export function debitsCsv(debits: Debit[]): string {
  const lines = [DEBITS_HEADER];
  for (const d of debits) lines.push(`${d.card},${d.taps},${d.charged}`);
  return lines.join('\n') + '\n';
}

export interface ChargeRow {
  ts: string;
  card: string;
  route: string;
  stop: string;
  fare: number;
  charged: number;
  reason: Reason;
}

export function parseCharges(text: string, name: string): ChargeRow[] {
  const lines = text.split('\n');
  if (lines[0] !== CHARGES_HEADER) throw new Error(`${name}: not a charges file`);
  const rows: ChargeRow[] = [];
  for (const line of lines.slice(1)) {
    if (line === '') continue;
    const [ts, card, route, stop, fare, charged, reason] = line.split(',');
    rows.push({ ts, card, route, stop, fare: Number(fare), charged: Number(charged), reason: reason as Reason });
  }
  return rows;
}
