// hours invoice against the month-end script on the same entries: the two must agree on every project's
// minutes, rounding, rate, and amount, and on the totals. The script bills +nobill entries, so it gets only
// the billed ones. Only this test runs Python; hours itself does not.
import assert from 'node:assert/strict';
import { spawnSync } from 'node:child_process';
import { mkdtempSync, readFileSync, rmSync, writeFileSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { test } from 'node:test';
import { bill } from '../src/commands/invoice.ts';
import { formatCents, formatPercent } from '../src/money.ts';
import { readRateCard } from '../src/rates.ts';
import { readTimesheets } from '../src/timesheet.ts';

const SHEETS = ['timesheets/2026-09-dana.txt', 'timesheets/2026-09-omar.txt'];
const python = spawnSync('python3', ['--version']);

test('invoice agrees with the month-end script', { skip: python.error ? 'no python3' : false }, () => {
  const dir = mkdtempSync(join(tmpdir(), 'hours-parity-'));
  try {
    const billed = join(dir, 'billed.txt');
    const lines = SHEETS.flatMap((f) => readFileSync(f, 'utf8').split('\n'));
    writeFileSync(billed, lines.filter((l) => !l.split(/\s+/).includes('+nobill')).join('\n'));
    const clients = readRateCard('rates.txt');
    const entries = readTimesheets(SHEETS);
    for (const client of clients.values()) {
      const r = spawnSync('python3', ['scripts/invoice.py', '--rates', 'rates.txt', '--client', client.id, '--month', '2026-09', '--json', billed], { encoding: 'utf8' });
      assert.equal(r.status, 0, r.stderr);
      const theirs = JSON.parse(r.stdout);
      const ours = bill(client, entries, '2026-09-01', '2026-09-30');
      assert.deepEqual(
        ours.projects.map((p) => [p.project, p.entries, p.minutes, p.billed, formatCents(p.rate), formatCents(p.amount)]),
        theirs.projects.map((p: Record<string, unknown>) => [p.project, p.entries, p.minutes, p.billed_minutes, p.rate, p.amount]),
        client.id,
      );
      assert.deepEqual(
        [formatCents(ours.subtotal), formatPercent(client.tax), formatCents(ours.tax), formatCents(ours.total)],
        [theirs.subtotal, theirs.tax_percent, theirs.tax, theirs.total],
        client.id,
      );
    }
  } finally {
    rmSync(dir, { recursive: true, force: true });
  }
});
