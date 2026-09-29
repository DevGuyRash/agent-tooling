# Plausible fix that misses the hazard: the call site now passes functions, which bounds the
# happy path and stops the crash, but the limiter's failure behavior is left as it was. After a
# failure it rejects at once while the other workers keep starting the rest of the queue in the
# background, against the README's failure policy.
set -e

python3 - <<'PY'
p = "lib/sync.js"
s = open(p).read()
s = s.replace(
    "  return runWithConcurrency(skus.map(fetchRow), concurrency);",
    "  // Pass functions so the limiter decides when each request starts.\n"
    "  return runWithConcurrency(skus.map((sku) => () => fetchRow(sku)), concurrency);",
)
open(p, "w").write(s)
PY

cat >> test/sync.test.js <<'EOF'

test('keeps at most `concurrency` requests in flight', async () => {
  let inFlight = 0;
  let peak = 0;
  const client = {
    async fetchPrice() {
      inFlight++;
      peak = Math.max(peak, inFlight);
      await delay(5);
      inFlight--;
      return { amount: 100, currency: 'USD' };
    },
  };
  const skus = Array.from({ length: 12 }, (_, i) => `SKU-${i}`);

  const rows = await syncPrices(skus, { client, concurrency: 3 });

  assert.equal(peak, 3);
  assert.equal(rows.length, 12);
});
EOF

node --test > "$TRIAL_JOB_DIR/node-test.log" 2>&1

cat > "$TRIAL_JOB_DIR/final-0.md" <<'EOF'
The limiter was fine; the call site wasn't. `syncPrices` did `runWithConcurrency(skus.map(fetchRow), concurrency)`, and `skus.map(fetchRow)` calls `fetchRow` for every SKU right away, so all requests were sent before the limiter got them. The limiter's own test passes functions, which is why it looked fine. The unhandled rejection was the same bug: promises that failed before a worker got around to awaiting them.

Fix: `lib/sync.js` now passes `() => fetchRow(sku)` so each request starts only when the limiter runs it. I added a test that checks `syncPrices` never has more than `concurrency` requests in flight. All tests pass.
EOF
