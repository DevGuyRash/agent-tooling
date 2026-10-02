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

// Taps are charged in the export's order, which is the order the back office received them in. The earlier
// charges are kept in typed arrays (card number, amount, whether the tap started a journey) so the look back
// over them is a tight loop with nothing allocated per tap.
export function chargeDay(taps: Tap[]): Charge[] {
  const charges: Charge[] = [];
  const cards = new Float64Array(taps.length);
  const amounts = new Int32Array(taps.length);
  const starts = new Uint8Array(taps.length);
  for (let i = 0; i < taps.length; i++) {
    const tap = taps[i];
    const card = Number(tap.card);
    let spent = 0;
    let start = -1;
    for (let k = i - 1; k >= 0; k--) {
      if (cards[k] !== card) continue;
      spent += amounts[k];
      if (start < 0 && starts[k] === 1) start = k;
    }
    cards[i] = card;
    if (start >= 0 && isTransfer(taps[start], tap)) {
      charges.push({ tap, charged: 0, reason: 'transfer' });
      continue;
    }
    const charged = Math.min(tap.fare, Math.max(0, dailyCap(tap.card) - spent));
    amounts[i] = charged;
    starts[i] = 1;
    charges.push({ tap, charged, reason: charged === tap.fare ? 'fare' : 'capped' });
  }
  return charges;
}
