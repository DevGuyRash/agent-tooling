#!/usr/bin/env node
import { mkdir, readFile, writeFile } from 'node:fs/promises';
import path from 'node:path';

import { loadConfig } from '../lib/config.js';
import { createPricingClient } from '../lib/pricing-client.js';
import { parseSkuList } from '../lib/skus.js';
import { syncPrices } from '../lib/sync.js';

async function main([input = 'data/skus.txt', output = 'out/prices.json']) {
  const config = loadConfig();
  const skus = parseSkuList(await readFile(input, 'utf8'));
  const client = createPricingClient({ baseUrl: config.baseUrl, timeoutMs: config.timeoutMs });

  const started = Date.now();
  const rows = await syncPrices(skus, { client, concurrency: config.concurrency });

  await mkdir(path.dirname(output), { recursive: true });
  await writeFile(output, `${JSON.stringify(rows, null, 2)}\n`);
  console.log(`wrote ${rows.length} prices to ${output} in ${Date.now() - started} ms`);
}

main(process.argv.slice(2)).catch((error) => {
  console.error(`price sync failed: ${error.message}`);
  process.exitCode = 1;
});
