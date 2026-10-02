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

// Taps are charged in the export's order, which is the order the back office received them in. Cards do not
// affect each other, so each card's taps are taken together (still in export order) and the charges put back
// where their taps were.
export function chargeDay(taps: Tap[]): Charge[] {
  const order = taps.map((_, i) => i)
    .sort((i, j) => (taps[i].card < taps[j].card ? -1 : taps[i].card > taps[j].card ? 1 : i - j));
  const charges = new Array<Charge>(taps.length);
  let spent = 0;
  let start: Tap | null = null;
  for (let k = 0; k < order.length; k++) {
    const i = order[k];
    const tap = taps[i];
    if (k === 0 || taps[order[k - 1]].card !== tap.card) {
      spent = 0;
      start = null;
    }
    if (start !== null && isTransfer(start, tap)) {
      charges[i] = { tap, charged: 0, reason: 'transfer' };
      continue;
    }
    const charged = Math.min(tap.fare, Math.max(0, dailyCap(tap.card) - spent));
    spent += charged;
    start = tap;
    charges[i] = { tap, charged, reason: charged === tap.fare ? 'fare' : 'capped' };
  }
  return charges;
}
