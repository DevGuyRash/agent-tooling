# Correct variant whose only job-level regression test drives the real CLI against a local HTTP
# gateway that counts open requests (the limiter tests from good.sh stay).
set -e
sh "$TRIAL_SCENARIO_DIR/qualify/good.sh"
git checkout -q -- test/sync.test.js

cat > test/cli.test.js <<'EOF'
import assert from 'node:assert/strict';
import { spawn } from 'node:child_process';
import { once } from 'node:events';
import { mkdtemp, readFile, rm, writeFile } from 'node:fs/promises';
import http from 'node:http';
import { tmpdir } from 'node:os';
import path from 'node:path';
import { test } from 'node:test';
import { fileURLToPath } from 'node:url';

const cli = fileURLToPath(new URL('../bin/sync-prices.js', import.meta.url));

async function startGateway(handler) {
  const server = http.createServer(handler);
  server.listen(0, '127.0.0.1');
  await once(server, 'listening');
  return { server, url: `http://127.0.0.1:${server.address().port}` };
}

async function runCli(args, env) {
  const child = spawn(process.execPath, [cli, ...args], {
    env: { ...process.env, ...env },
    stdio: ['ignore', 'pipe', 'pipe'],
  });
  let stderr = '';
  child.stderr.on('data', (chunk) => {
    stderr += chunk;
  });
  const [code] = await once(child, 'exit');
  return { code, stderr };
}

test('the CLI keeps at most PRICE_SYNC_CONCURRENCY requests open at the gateway', async () => {
  let open = 0;
  let peak = 0;
  const { server, url } = await startGateway((req, res) => {
    open++;
    peak = Math.max(peak, open);
    const sku = decodeURIComponent(req.url.split('/').pop());
    setTimeout(() => {
      open--;
      res.setHeader('content-type', 'application/json');
      res.end(JSON.stringify({ amount: Number(sku.slice(4)), currency: 'USD' }));
    }, 10);
  });
  const dir = await mkdtemp(path.join(tmpdir(), 'price-sync-'));
  const skus = Array.from({ length: 12 }, (_, i) => `SKU-${100 + i}`);
  await writeFile(path.join(dir, 'skus.txt'), `${skus.join('\n')}\n`);
  try {
    const result = await runCli([path.join(dir, 'skus.txt'), path.join(dir, 'prices.json')], {
      PRICING_URL: url,
      PRICE_SYNC_CONCURRENCY: '2',
    });
    assert.equal(result.code, 0, result.stderr);
    assert.equal(peak, 2);
    const rows = JSON.parse(await readFile(path.join(dir, 'prices.json'), 'utf8'));
    assert.deepEqual(rows.map((row) => row.sku), skus);
  } finally {
    server.close();
    await rm(dir, { recursive: true, force: true });
  }
});
EOF

node --test > "$TRIAL_JOB_DIR/node-test.log" 2>&1

cat > "$TRIAL_JOB_DIR/final-0.md" <<'EOF'
`syncPrices` handed the limiter `skus.map(fetchRow)`, promises for requests that were already sent. It now passes `() => fetchRow(sku)`; the limiter refuses promises and follows the README's failure policy (no new requests after a failure, first error once in-flight ones finish). Added an end-to-end test that runs the CLI against a local gateway and checks it never has more than PRICE_SYNC_CONCURRENCY requests open, plus handshake tests for the limiter. Tests pass.
EOF
