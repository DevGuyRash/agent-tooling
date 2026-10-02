// What billing debits from each card's account for the day: one line per card, in the order the cards first
// appear in the charges.

import type { Charge } from './fares.ts';

export interface Debit {
  card: string;
  taps: number;
  charged: number;
}

export function cardDebits(charges: Charge[]): Debit[] {
  const debits: Debit[] = [];
  const cards = new Float64Array(charges.length);
  for (const { tap, charged } of charges) {
    const card = Number(tap.card);
    let k = debits.length - 1;
    while (k >= 0 && cards[k] !== card) k--;
    if (k < 0) {
      k = debits.length;
      cards[k] = card;
      debits.push({ card: tap.card, taps: 0, charged: 0 });
    }
    debits[k].taps += 1;
    debits[k].charged += charged;
  }
  return debits;
}
