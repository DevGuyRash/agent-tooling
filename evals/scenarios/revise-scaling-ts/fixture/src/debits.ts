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
  for (const { tap, charged } of charges) {
    let debit = debits.find((d) => d.card === tap.card);
    if (!debit) {
      debit = { card: tap.card, taps: 0, charged: 0 };
      debits.push(debit);
    }
    debit.taps += 1;
    debit.charged += charged;
  }
  return debits;
}
