# Review round 1 counterexample (task-factory): a correct fix that extracts task creation into an
# exported priceTasks() and pins it with handshake tests on the factory and the limiter. The
# regression measure must credit these tests (the eager-start wrapper pre-starts returned tasks).
set -e
python3 - <<'PY'
p = "lib/limit.js"; s = open(p).read()
s = s.replace("""  let next = 0;

  async function worker() {
    while (next < tasks.length) {
      const index = next++;
      const task = tasks[index];
      results[index] = await (typeof task === 'function' ? task() : task);
    }
  }
""", """  let next = 0;
  let failed = false;
  let firstError;

  async function worker() {
    while (!failed && next < tasks.length) {
      const index = next++;
      const task = tasks[index];
      if (typeof task !== 'function') {
        throw new TypeError('runWithConcurrency expects functions that start the work');
      }
      try {
        results[index] = await task();
      } catch (error) {
        if (!failed) {
          failed = true;
          firstError = error;
        }
      }
    }
  }
""").replace("  await Promise.all(workers);\n  return results;", "  await Promise.all(workers);\n  if (failed) throw firstError;\n  return results;")
open(p, "w").write(s)
p = "lib/sync.js"; s = open(p).read()
s = s.replace("""export async function syncPrices(skus, { client, concurrency = DEFAULT_CONCURRENCY }) {
  const fetchRow = async (sku) => {
    const quote = await client.fetchPrice(sku);
    return { sku, priceCents: quote.amount, currency: quote.currency };
  };

  return runWithConcurrency(skus.map(fetchRow), concurrency);
}""", """export async function syncPrices(skus, { client, concurrency = DEFAULT_CONCURRENCY }) {
  return runWithConcurrency(priceTasks(skus, client), concurrency);
}

/**
 * One task per SKU. A task is a function: nothing is sent until the limiter calls it.
 */
export function priceTasks(skus, client) {
  return skus.map((sku) => async () => {
    const quote = await client.fetchPrice(sku);
    return { sku, priceCents: quote.amount, currency: quote.currency };
  });
}""")
open(p, "w").write(s)
PY
cat > test/price-tasks.test.js <<'EOF'
import assert from 'node:assert/strict';
import { test } from 'node:test';

import { runWithConcurrency } from '../lib/limit.js';
import { priceTasks } from '../lib/sync.js';

function heldClient() {
  const open = new Map();
  const started = [];
  return {
    started,
    fetchPrice(sku) {
      started.push(sku);
      return new Promise((resolve) => open.set(sku, resolve));
    },
    answer(sku) {
      open.get(sku)({ amount: 1, currency: 'USD' });
    },
  };
}
const settle = () => new Promise((resolve) => setImmediate(resolve));

test('creating the price tasks sends no request', () => {
  const client = heldClient();
  const tasks = priceTasks(['A', 'B', 'C'], client);
  assert.equal(tasks.length, 3);
  assert.ok(tasks.every((t) => typeof t === 'function'));
  assert.deepEqual(client.started, []);
});

test('the limiter starts price tasks only as slots free up', async () => {
  const client = heldClient();
  const run = runWithConcurrency(priceTasks(['A', 'B', 'C', 'D'], client), 2);
  await settle();
  assert.deepEqual(client.started, ['A', 'B']);
  client.answer('A');
  await settle();
  assert.deepEqual(client.started, ['A', 'B', 'C']);
  client.answer('B');
  client.answer('C');
  await settle();
  client.answer('D');
  assert.equal((await run).length, 4);
});

test('the limiter refuses promises that have already started', async () => {
  await assert.rejects(runWithConcurrency([Promise.resolve(1)], 1), TypeError);
});
EOF
node --test > "$TRIAL_JOB_DIR/node-test.log" 2>&1
printf '%s\n' "syncPrices started every request before the limiter saw it; tasks are now functions built by priceTasks(), the limiter refuses started promises, and it follows the README failure policy. Added handshake tests." > "$TRIAL_JOB_DIR/final-0.md"
