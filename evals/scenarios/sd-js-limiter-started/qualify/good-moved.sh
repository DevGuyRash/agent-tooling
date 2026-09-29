# Correct variant that moves syncPrices into lib/price-fetcher.js (lib/sync.js re-exports it) and
# tests it through the new module, so the check has to find where syncPrices is defined.
set -e
sh "$TRIAL_SCENARIO_DIR/qualify/good.sh"
git mv -f lib/sync.js lib/price-fetcher.js
cat > lib/sync.js <<'EOF'
export { DEFAULT_CONCURRENCY, syncPrices } from './price-fetcher.js';
EOF
sed -i "s#from '../lib/sync.js'#from '../lib/price-fetcher.js'#" test/sync.test.js
node --test > "$TRIAL_JOB_DIR/node-test.log" 2>&1

cat > "$TRIAL_JOB_DIR/final-0.md" <<'EOF'
Moved the job logic to `lib/price-fetcher.js` (`lib/sync.js` re-exports it). It passes the limiter functions instead of already-started requests; the limiter refuses promises and implements the README's failure policy. Handshake tests cover admission, refill, order, and the failure path. Tests pass.
EOF
