import assert from 'node:assert/strict';
import { test } from 'node:test';

import { loadConfig } from '../lib/config.js';
import { parseSkuList } from '../lib/skus.js';

test('uses defaults when only PRICING_URL is set', () => {
  assert.deepEqual(loadConfig({ PRICING_URL: 'https://pricing.test' }), {
    baseUrl: 'https://pricing.test',
    concurrency: 4,
    timeoutMs: 10_000,
  });
});

test('reads the concurrency cap from the environment', () => {
  const config = loadConfig({ PRICING_URL: 'https://pricing.test', PRICE_SYNC_CONCURRENCY: '2' });
  assert.equal(config.concurrency, 2);
});

test('rejects a concurrency cap that is not a positive integer', () => {
  for (const value of ['0', '-1', '2.5', 'four']) {
    assert.throws(
      () => loadConfig({ PRICING_URL: 'https://pricing.test', PRICE_SYNC_CONCURRENCY: value }),
      /PRICE_SYNC_CONCURRENCY must be a positive integer/,
    );
  }
});

test('requires PRICING_URL', () => {
  assert.throws(() => loadConfig({}), /PRICING_URL is required/);
});

test('parses the SKU file, skipping blanks and comments', () => {
  assert.deepEqual(parseSkuList('# export 2026-09-28\nA1\n\n  B2  \r\n# discontinued\nC3\n'), ['A1', 'B2', 'C3']);
});
