# Partial fix: the reference code change, but the only new tests are at the limiter level. The
# limiter was already correct for functions, so no test exercises the call site where requests
# were started eagerly, and reintroducing that bug would pass the suite.
set -e
sh "$TRIAL_SCENARIO_DIR/qualify/good.sh"
git checkout -q -- test/sync.test.js
node --test > "$TRIAL_JOB_DIR/node-test.log" 2>&1

cat > "$TRIAL_JOB_DIR/final-0.md" <<'EOF'
`syncPrices` passed `skus.map(fetchRow)` (requests already sent) to the limiter; it now passes `() => fetchRow(sku)`. The limiter refuses promises and follows the README's failure policy: no new tasks after a failure, then the first error once running tasks settle. Added deterministic limiter tests for refusal, refill, and the failure path. Tests pass.
EOF
