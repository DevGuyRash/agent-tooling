// One worker's share of the cards: see parallel.ts.

import { parentPort, workerData } from 'node:worker_threads';
import { cardDebits } from './debits.ts';
import { chargeDay } from './fares.ts';
import type { ShardResult } from './parallel.ts';
import { dropDuplicates, type Tap } from './taps.ts';

const { kept, dropped } = dropDuplicates(workerData as Tap[]);
const charges = chargeDay(kept);
const firsts = new Map<string, number>();
for (const c of charges) if (!firsts.has(c.tap.card)) firsts.set(c.tap.card, c.tap.line);
const result: ShardResult = {
  dropped,
  charges: charges.map((c) => ({ line: c.tap.line, charged: c.charged, reason: c.reason })),
  debits: cardDebits(charges).map((debit) => ({ first: firsts.get(debit.card)!, debit })),
};
parentPort!.postMessage(result);
