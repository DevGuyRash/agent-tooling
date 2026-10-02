// A card's day as the customer-service desk reads it out: tapfare statement CHARGES.csv --card CARD.

import { formatCents } from './money.ts';
import type { ChargeRow } from './output.ts';
import { clock, parseTimestamp, serviceDay } from './serviceday.ts';

function grouped(card: string): string {
  return card.replace(/(\d{4})(?=\d)/g, '$1 ');
}

export function statement(rows: ChargeRow[], card: string): string | null {
  const mine = rows.filter((r) => r.card === card);
  if (mine.length === 0) return null;
  const day = serviceDay(parseTimestamp(mine[0].ts) ?? 0);
  const lines = [`Card ${grouped(card)}, service day ${day}`];
  let total = 0;
  for (const r of mine) {
    lines.push(`${clock(r.ts)}  route ${r.route.padEnd(4)} ${r.stop}  ${formatCents(r.charged).padStart(6)}  ${r.reason}`);
    total += r.charged;
  }
  lines.push(`total${formatCents(total).padStart(27)}`);
  return lines.join('\n') + '\n';
}
