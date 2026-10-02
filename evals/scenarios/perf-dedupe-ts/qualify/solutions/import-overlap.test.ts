import { test } from 'node:test';
import assert from 'node:assert/strict';
import { spawnSync } from 'node:child_process';
import { mkdtempSync, readFileSync, rmSync, writeFileSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { fileURLToPath } from 'node:url';

const BIN = fileURLToPath(new URL('../bin/ledgerkit.ts', import.meta.url));
const HEADER = 'Date,Time,Store,Terminal,Card,Amount,Type\n';

function importInto(t: { after: (fn: () => void) => void }, ledger: string, exportText: string) {
  const dir = mkdtempSync(join(tmpdir(), 'ledgerkit-overlap-'));
  t.after(() => rmSync(dir, { recursive: true, force: true }));
  const ledgerPath = join(dir, 'ledger.csv');
  const exportPath = join(dir, 'export.csv');
  writeFileSync(ledgerPath, ledger);
  writeFileSync(exportPath, HEADER + exportText);
  const r = spawnSync(process.execPath, [BIN, 'import', exportPath, '--ledger', ledgerPath], { encoding: 'utf8' });
  assert.equal(r.status, 0, r.stderr);
  return readFileSync(ledgerPath, 'utf8');
}

test('a rolling export adds only what the ledger does not have', (t) => {
  const ledger = 'ts,store,terminal,card,amount_cents\n2026-09-28T07:41,S14,2,5050,480\n';
  const after = importInto(
    t,
    ledger,
    '2026-09-28,07:41,S14,2,************5050,4.80,SALE\n2026-09-29,08:00,S14,2,************5050,4.80,SALE\n',
  );
  assert.equal(after, ledger + '2026-09-29T08:00,S14,2,5050,480\n');
});

test('identical lines are counted, not collapsed', (t) => {
  const ledger = 'ts,store,terminal,card,amount_cents\n2026-09-28T07:41,S14,2,5050,480\n2026-09-28T07:41,S14,2,5050,480\n';
  const line = '2026-09-28,07:41,S14,2,************5050,4.80,SALE\n';
  assert.equal(importInto(t, ledger, line.repeat(3)), ledger + '2026-09-28T07:41,S14,2,5050,480\n');
  assert.equal(importInto(t, ledger, line), ledger);
});

test('a refund is not the same transaction as the sale', (t) => {
  const ledger = 'ts,store,terminal,card,amount_cents\n2026-09-28T10:00,S10,1,1234,450\n';
  const after = importInto(t, ledger, '2026-09-28,10:00,S10,1,************1234,4.50,REFUND\n');
  assert.equal(after, ledger + '2026-09-28T10:00,S10,1,1234,-450\n');
});
