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

export function dropDuplicates(taps: Tap[]): { kept: Tap[]; dropped: number } {
  const kept: Tap[] = [];
  let dropped = 0;
  // The comparison runs over typed arrays of the kept taps' times and card numbers (twelve digits fit a
  // double exactly), so most comparisons are one number; sameTap settles the rest.
  const times = new Float64Array(taps.length);
  const cards = new Float64Array(taps.length);
  outer: for (const tap of taps) {
    const at = tap.at;
    const card = Number(tap.card);
    for (let k = kept.length - 1; k >= 0; k--) {
      if (times[k] === at && cards[k] === card && sameTap(kept[k], tap)) {
        dropped++;
        continue outer;
      }
    }
    times[kept.length] = at;
    cards[kept.length] = card;
    kept.push(tap);
  }
  return { kept, dropped };
}
