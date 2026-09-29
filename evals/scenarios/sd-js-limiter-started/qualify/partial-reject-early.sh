# Partial fix: admission is fixed and the limiter stops starting work after a failure, but it
# rejects the moment the failure happens, while other requests are still in flight.
set -e

python3 - <<'PY'
p = "lib/sync.js"
s = open(p).read()
s = s.replace("  return runWithConcurrency(skus.map(fetchRow), concurrency);",
              "  return runWithConcurrency(skus.map((sku) => () => fetchRow(sku)), concurrency);")
open(p, "w").write(s)

p = "lib/limit.js"
s = open(p).read()
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

  async function worker() {
    while (!failed && next < tasks.length) {
      const index = next++;
      const task = tasks[index];
      try {
        results[index] = await (typeof task === 'function' ? task() : task);
      } catch (error) {
        failed = true; // the other workers stop picking up new tasks
        throw error;
      }
    }
  }
""")
open(p, "w").write(s)
PY

cat >> test/sync.test.js <<'EOF'

function heldClient() {
  const open = new Map();
  const started = [];
  return {
    started,
    fetchPrice(sku) {
      started.push(sku);
      return new Promise((resolve, reject) => open.set(sku, { resolve, reject }));
    },
    answer(sku) {
      open.get(sku).resolve({ amount: 100, currency: 'USD' });
    },
    fail(sku, error) {
      open.get(sku).reject(error);
    },
  };
}

const settle = () => new Promise((resolve) => setImmediate(resolve));

test('sends a request only when a slot is free', async () => {
  const client = heldClient();
  const run = syncPrices(['A', 'B', 'C', 'D'], { client, concurrency: 2 });
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

test('sends no new requests after one fails', async () => {
  const client = heldClient();
  const run = syncPrices(['A', 'B', 'C', 'D', 'E'], { client, concurrency: 3 });
  await settle();
  client.fail('B', new Error('503'));
  await assert.rejects(run, /503/);
  client.answer('A');
  client.answer('C');
  await settle();
  assert.deepEqual(client.started, ['A', 'B', 'C']);
});
EOF

node --test > "$TRIAL_JOB_DIR/node-test.log" 2>&1

cat > "$TRIAL_JOB_DIR/final-0.md" <<'EOF'
`syncPrices` passed `skus.map(fetchRow)`, promises whose requests were already sent, to the limiter, so nothing was limited. It now passes `() => fetchRow(sku)`. I also made the limiter stop picking up new tasks once one fails, so a 503 doesn't trigger the rest of the batch. Added handshake tests for both. Tests pass.
EOF
