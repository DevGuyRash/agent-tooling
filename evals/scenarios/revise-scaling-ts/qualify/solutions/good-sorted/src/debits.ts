// What billing debits from each card's account for the day: one line per card, in the order the cards first
// appear in the charges.

import type { Charge } from './fares.ts';

export interface Debit {
  card: string;
  taps: number;
  charged: number;
}

export function cardDebits(charges: Charge[]): Debit[] {
  const card = (i: number) => charges[i].tap.card;
  const order = charges.map((_, i) => i).sort((i, j) => (card(i) < card(j) ? -1 : card(i) > card(j) ? 1 : i - j));
  const found: { first: number; debit: Debit }[] = [];
  for (let k = 0; k < order.length; k++) {
    const { tap, charged } = charges[order[k]];
    if (k === 0 || card(order[k - 1]) !== tap.card) found.push({ first: order[k], debit: { card: tap.card, taps: 0, charged: 0 } });
    const { debit } = found[found.length - 1];
    debit.taps += 1;
    debit.charged += charged;
  }
  return found.sort((a, b) => a.first - b.first).map((f) => f.debit);
}
