import assert from 'node:assert/strict';
import { test } from 'node:test';

import { createPricingClient, PricingError } from '../lib/pricing-client.js';

function respondWith(status, body) {
  const calls = [];
  const fetch = async (url, init) => {
    calls.push({ url: String(url), init });
    return new Response(JSON.stringify(body), { status, headers: { 'content-type': 'application/json' } });
  };
  return { calls, fetch };
}

test('requests the SKU from the prices endpoint', async () => {
  const { calls, fetch } = respondWith(200, { amount: 1299, currency: 'USD' });
  const client = createPricingClient({ baseUrl: 'https://pricing.test', fetch });

  assert.deepEqual(await client.fetchPrice('AB/12'), { amount: 1299, currency: 'USD' });
  assert.equal(calls[0].url, 'https://pricing.test/v1/prices/AB%2F12');
});

test('turns an HTTP error into a PricingError with the status', async () => {
  const { fetch } = respondWith(503, { error: 'overloaded' });
  const client = createPricingClient({ baseUrl: 'https://pricing.test', fetch });

  await assert.rejects(client.fetchPrice('A1'), (error) => {
    assert.ok(error instanceof PricingError);
    assert.equal(error.status, 503);
    assert.equal(error.sku, 'A1');
    return true;
  });
});

test('rejects a price without an integer amount', async () => {
  const { fetch } = respondWith(200, { amount: '12.99', currency: 'USD' });
  const client = createPricingClient({ baseUrl: 'https://pricing.test', fetch });

  await assert.rejects(client.fetchPrice('A1'), /malformed price for A1/);
});

test('wraps network failures', async () => {
  const fetch = async () => {
    throw new TypeError('fetch failed');
  };
  const client = createPricingClient({ baseUrl: 'https://pricing.test', fetch });

  await assert.rejects(client.fetchPrice('A1'), /request for A1 failed: fetch failed/);
});
