import assert from 'node:assert/strict';
import { test } from 'node:test';
import { setTimeout as delay } from 'node:timers/promises';

import { syncPrices } from '../lib/sync.js';

function fakeClient(prices, { latency = () => 1 } = {}) {
  const requested = [];
  return {
    requested,
    async fetchPrice(sku) {
      requested.push(sku);
      await delay(latency(sku));
      if (!(sku in prices)) {
        throw new Error(`unknown sku ${sku}`);
      }
      return { amount: prices[sku], currency: 'USD' };
    },
  };
}

test('returns one row per SKU in input order', async () => {
  const latency = { A1: 15, B2: 1, C3: 5 };
  const client = fakeClient({ A1: 1299, B2: 450, C3: 9999 }, { latency: (sku) => latency[sku] });

  const rows = await syncPrices(['A1', 'B2', 'C3'], { client, concurrency: 2 });

  assert.deepEqual(rows, [
    { sku: 'A1', priceCents: 1299, currency: 'USD' },
    { sku: 'B2', priceCents: 450, currency: 'USD' },
    { sku: 'C3', priceCents: 9999, currency: 'USD' },
  ]);
});

test('requests every SKU once', async () => {
  const client = fakeClient({ A1: 1, B2: 2, C3: 3, D4: 4 });

  await syncPrices(['A1', 'B2', 'C3', 'D4'], { client, concurrency: 2 });

  assert.deepEqual([...client.requested].sort(), ['A1', 'B2', 'C3', 'D4']);
});

test('rejects when the pricing service fails', async () => {
  const client = fakeClient({ A1: 1, C3: 3 });

  await assert.rejects(syncPrices(['A1', 'B2', 'C3'], { client, concurrency: 2 }), /unknown sku B2/);
});

test('an empty SKU list makes no requests', async () => {
  const client = fakeClient({});

  assert.deepEqual(await syncPrices([], { client }), []);
  assert.equal(client.requested.length, 0);
});
