// The tap export: see docs/tap-export.md.

import { parseTimestamp } from './serviceday.ts';

export const HEADER = 'ts,card,route,stop,fare_cents,batch';

export interface Tap {
  line: number;
  ts: string;
  at: number; // seconds, see serviceday.ts
  card: string; // twelve digits, no spaces
  route: string;
  stop: string;
  fare: number; // cents
  batch: string;
}

const ROUTE = /^[A-Z0-9]{1,4}$/;
const STOP = /^[A-Z]{2}\d{4}$/;
const FARE = /^\d{1,5}$/;

// Older readers print the card number in groups of four ("4402 7713 0981").
export function normalizeCard(raw: string): string | null {
  const card = raw.replaceAll(' ', '');
  return /^\d{12}$/.test(card) ? card : null;
}

export function parseTaps(text: string, name: string): { taps: Tap[]; errors: string[] } {
  const lines = text.split('\n').map((l) => (l.endsWith('\r') ? l.slice(0, -1) : l));
  const taps: Tap[] = [];
  const errors: string[] = [];
  if (lines[0] !== HEADER) {
    errors.push(`${name}: line 1: expected the header ${HEADER}`);
    return { taps, errors };
  }
  for (let i = 1; i < lines.length; i++) {
    const line = lines[i];
    if (line === '') continue;
    const where = `${name}: line ${i + 1}`;
    const fields = line.split(',');
    if (fields.length !== 6) {
      errors.push(`${where}: expected 6 fields, found ${fields.length}`);
      continue;
    }
    const [ts, rawCard, route, stop, fare, batch] = fields;
    const at = parseTimestamp(ts);
    const card = normalizeCard(rawCard);
    if (at === null) errors.push(`${where}: bad time '${ts}'`);
    else if (card === null) errors.push(`${where}: bad card number '${rawCard}'`);
    else if (!ROUTE.test(route)) errors.push(`${where}: bad route '${route}'`);
    else if (!STOP.test(stop)) errors.push(`${where}: bad stop '${stop}'`);
    else if (!FARE.test(fare)) errors.push(`${where}: bad fare '${fare}'`);
    else if (batch === '') errors.push(`${where}: missing batch`);
    else taps.push({ line: i + 1, ts, at, card, route, stop, fare: Number(fare), batch });
  }
  return { taps, errors };
}

// Readers that lose their connection mid-upload send the batch again, and the back office re-sends taps it
// was unsure about, so the same tap can be in the export twice. It is the same tap when the time, card,
// route, stop and fare match; the batch it came in does not matter.
export function sameTap(a: Tap, b: Tap): boolean {
  return a.at === b.at && a.card === b.card && a.route === b.route && a.stop === b.stop && a.fare === b.fare;
}

function byText(a: string, b: string): number {
  return a < b ? -1 : a > b ? 1 : 0;
}

function byTapFields(a: Tap, b: Tap): number {
  return a.at - b.at || byText(a.card, b.card) || byText(a.route, b.route) || byText(a.stop, b.stop) || a.fare - b.fare;
}

// Sorting the taps by the fields sameTap compares (export order among equals) puts every copy of a tap right
// after its first line, so each tap only has to be compared with its neighbour.
export function dropDuplicates(taps: Tap[]): { kept: Tap[]; dropped: number } {
  const order = taps.map((_, i) => i).sort((i, j) => byTapFields(taps[i], taps[j]) || i - j);
  const copy = new Uint8Array(taps.length);
  for (let k = 1; k < order.length; k++) {
    if (sameTap(taps[order[k - 1]], taps[order[k]])) copy[order[k]] = 1;
  }
  const kept = taps.filter((_, i) => copy[i] === 0);
  return { kept, dropped: taps.length - kept.length };
}
