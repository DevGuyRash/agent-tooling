// What billing debits from each card's account for the day: one line per card, in the order the cards first
// appear in the charges.

import type { Charge } from './fares.ts';

export interface Debit {
  card: string;
  taps: number;
  charged: number;
}

export function cardDebits(charges: Charge[]): Debit[] {
  const debits = new Map<string, Debit>(); // a Map keeps the order cards were added in
  for (const { tap, charged } of charges) {
    let debit = debits.get(tap.card);
    if (debit === undefined) {
      debit = { card: tap.card, taps: 0, charged: 0 };
      debits.set(tap.card, debit);
    }
    debit.taps += 1;
    debit.charged += charged;
  }
  return [...debits.values()];
}
