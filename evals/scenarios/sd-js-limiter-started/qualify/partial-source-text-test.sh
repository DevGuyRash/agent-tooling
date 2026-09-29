# Review round 1 counterexample (source-text): a correct fix whose only added test asserts the source
# text of lib/sync.js. It passes the required checks, but the regression measure must not credit it:
# the test also fails under the neutral wrapper, so it cannot observe when requests start.
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
      try {
        results[index] = await (typeof task === 'function' ? task() : task);
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
s = s.replace("  return runWithConcurrency(skus.map(fetchRow), concurrency);",
              "  return runWithConcurrency(skus.map((sku) => () => fetchRow(sku)), concurrency);")
open(p, "w").write(s)
PY
cat > test/sync-source.test.js <<'EOF'
import assert from 'node:assert/strict';
import { readFile } from 'node:fs/promises';
import { test } from 'node:test';

test('syncPrices hands the limiter functions, not started requests', async () => {
  const source = await readFile(new URL('../lib/sync.js', import.meta.url), 'utf8');
  assert.match(source, /skus\.map\(\(sku\) => \(\) => fetchRow\(sku\)\)/);
});
EOF
node --test > "$TRIAL_JOB_DIR/node-test.log" 2>&1
printf '%s\n' "Fixed the call site and the failure policy; added a guard test." > "$TRIAL_JOB_DIR/final-0.md"
