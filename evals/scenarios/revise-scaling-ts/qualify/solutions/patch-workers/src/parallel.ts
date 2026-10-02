// The day's taps split across one worker per CPU. Cards never affect each other (duplicates share their
// card too), so each worker takes every tap of its share of the cards, in export order, and the results are
// put back together in export order.

import { availableParallelism } from 'node:os';
import { Worker } from 'node:worker_threads';
import type { Debit } from './debits.ts';
import type { Charge, Reason } from './fares.ts';
import type { Tap } from './taps.ts';

export interface ShardResult {
  dropped: number;
  charges: { line: number; charged: number; reason: Reason }[];
  debits: { first: number; debit: Debit }[]; // first: the line of the card's first charge
}

function shardOf(card: string, shards: number): number {
  let h = 0;
  for (let i = 0; i < card.length; i++) h = (h * 31 + card.charCodeAt(i)) >>> 0;
  return h % shards;
}

function runShard(taps: Tap[]): Promise<ShardResult> {
  return new Promise((resolve, reject) => {
    const worker = new Worker(new URL('./charge-worker.ts', import.meta.url), { workerData: taps });
    worker.once('message', resolve);
    worker.once('error', reject);
  });
}

export async function chargeInParallel(taps: Tap[]): Promise<{ dropped: number; charges: Charge[]; debits: Debit[] }> {
  const count = Math.max(1, availableParallelism());
  const shards: Tap[][] = Array.from({ length: count }, () => []);
  for (const tap of taps) shards[shardOf(tap.card, count)].push(tap);
  const results = await Promise.all(shards.map(runShard));
  const byLine = new Map(taps.map((t) => [t.line, t]));
  const charges = results.flatMap((r) => r.charges).sort((a, b) => a.line - b.line)
    .map((c) => ({ tap: byLine.get(c.line)!, charged: c.charged, reason: c.reason }));
  const debits = results.flatMap((r) => r.debits).sort((a, b) => a.first - b.first).map((d) => d.debit);
  return { dropped: results.reduce((n, r) => n + r.dropped, 0), charges, debits };
}
