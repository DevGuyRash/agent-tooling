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

// Taps are charged in the export's order, which is the order the back office received them in.
export function chargeDay(taps: Tap[]): Charge[] {
  const charges: Charge[] = [];
  for (const tap of taps) {
    const earlier = charges.filter((c) => c.tap.card === tap.card);
    const spent = earlier.reduce((sum, c) => sum + c.charged, 0);
    const start = earlier.filter((c) => c.reason !== 'transfer').at(-1);
    if (start && isTransfer(start.tap, tap)) {
      charges.push({ tap, charged: 0, reason: 'transfer' });
      continue;
    }
    const charged = Math.min(tap.fare, Math.max(0, dailyCap(tap.card) - spent));
    charges.push({ tap, charged, reason: charged === tap.fare ? 'fare' : 'capped' });
  }
  return charges;
}
