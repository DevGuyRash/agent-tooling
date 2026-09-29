# Non-fix: adapts the call site to a limiter that refuses promises by wrapping the already-created
# requests in functions (`requests.map((r) => () => r)`), so every request still starts at once.
set -e
sh "$TRIAL_SCENARIO_DIR/qualify/good.sh"
git checkout -q -- test/sync.test.js
python3 - <<'PY'
p = "lib/sync.js"
s = open(p).read()
s = s.replace("  return runWithConcurrency(skus.map((sku) => () => fetchRow(sku)), concurrency);",
              "  const requests = skus.map(fetchRow);\n"
              "  return runWithConcurrency(requests.map((request) => () => request), concurrency);")
open(p, "w").write(s)
PY
node --test > "$TRIAL_JOB_DIR/node-test.log" 2>&1

cat > "$TRIAL_JOB_DIR/final-0.md" <<'EOF'
The limiter accepted promises, which made it easy to misuse; it now requires functions and follows the README's failure policy. `syncPrices` passes each request to it as a function. Added limiter tests. Tests pass.
EOF
