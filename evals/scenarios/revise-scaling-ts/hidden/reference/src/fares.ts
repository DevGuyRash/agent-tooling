// The fare rules of docs/fares.md, applied to one service day's taps.

import type { Tap } from './taps.ts';

export const DAILY_CAP = 720;
export const CONCESSION_DAILY_CAP = 360;
export const TRANSFER_SECONDS = 60 * 60;

export type Reason = 'fare' | 'transfer' | 'capped';

export interface Charge {
  tap: Tap;
  charged: number;
  reason: Reason;
}

export function dailyCap(card: string): number {
  return card.startsWith('9') ? CONCESSION_DAILY_CAP : DAILY_CAP;
}

function isTransfer(start: Tap, tap: Tap): boolean {
  const gap = tap.at - start.at;
  return gap >= 0 && gap <= TRANSFER_SECONDS;
}

// Taps are charged in the export's order, which is the order the back office received them in. Each card's
// day so far is kept as it goes: what it has been charged and the tap that started its current journey.
export function chargeDay(taps: Tap[]): Charge[] {
  const cards = new Map<string, { spent: number; start: Tap | null }>();
  const charges: Charge[] = [];
  for (const tap of taps) {
    let card = cards.get(tap.card);
    if (card === undefined) {
      card = { spent: 0, start: null };
      cards.set(tap.card, card);
    }
    if (card.start !== null && isTransfer(card.start, tap)) {
      charges.push({ tap, charged: 0, reason: 'transfer' });
      continue;
    }
    const charged = Math.min(tap.fare, Math.max(0, dailyCap(tap.card) - card.spent));
    card.spent += charged;
    card.start = tap;
    charges.push({ tap, charged, reason: charged === tap.fare ? 'fare' : 'capped' });
  }
  return charges;
}
