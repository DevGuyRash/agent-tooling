// hours invoice. The month-end script (scripts/invoice.py) already reads the rate card and does the rounding,
// rates, and amounts, and it is tested, so hours reuses it: hours checks the command line and picks the entries
// (period, +nobill), the script bills them, and hours lays out the result.

import { spawnSync } from 'node:child_process';
import { mkdtempSync, rmSync, writeFileSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { fileURLToPath } from 'node:url';
import { parseArgs } from 'node:util';
import { daysInMonth, isDate } from '../dates.ts';
import { formatMinutes } from '../duration.ts';
import { failure, ok, type Result, usageError } from '../result.ts';
import { renderTable } from '../table.ts';
import { readTimesheets } from '../timesheet.ts';

const INVOICE_USAGE =
  'usage: hours invoice --client CLIENT --rates FILE (--month YYYY-MM | --from DATE --to DATE) TIMESHEET...';

const SCRIPT = fileURLToPath(new URL('../../scripts/invoice.py', import.meta.url));
const MONTH = /^(\d{4})-(\d{2})$/;

interface Billed {
  name: string;
  currency: string;
  projects: { project: string; entries: number; minutes: number; billed_minutes: number; rate: string; amount: string }[];
  subtotal: string;
  tax_percent: string;
  tax: string;
  total: string;
}

function script(args: string[]): { status: number; stdout: string; stderr: string } {
  const r = spawnSync('python3', [SCRIPT, ...args], { encoding: 'utf8' });
  if (r.error) throw r.error;
  return { status: r.status ?? 1, stdout: r.stdout, stderr: r.stderr };
}

export function helperInvoice(args: string[]): Result {
  const bad = (message: string) => usageError('invoice', message, INVOICE_USAGE);
  let values: { client?: string; rates?: string; month?: string; from?: string; to?: string };
  let files: string[];
  try {
    const parsed = parseArgs({
      args,
      options: {
        client: { type: 'string' },
        rates: { type: 'string' },
        month: { type: 'string' },
        from: { type: 'string' },
        to: { type: 'string' },
      },
      allowPositionals: true,
      strict: true,
    });
    values = parsed.values;
    files = parsed.positionals;
  } catch (error) {
    return bad((error as Error).message);
  }
  const { client, rates, month, from, to } = values;
  if (client === undefined) return bad('--client is required');
  if (rates === undefined) return bad('--rates is required');
  let first: string;
  let last: string;
  if (month !== undefined) {
    if (from !== undefined || to !== undefined) return bad('give either --month or --from and --to');
    const m = MONTH.exec(month);
    if (!m || Number(m[2]) < 1 || Number(m[2]) > 12) return bad(`bad month "${month}"`);
    first = `${month}-01`;
    last = `${month}-${String(daysInMonth(Number(m[1]), Number(m[2]))).padStart(2, '0')}`;
  } else if (from !== undefined && to !== undefined) {
    if (!isDate(from) || !isDate(to)) return bad('dates are YYYY-MM-DD');
    if (from > to) return bad('--from is after --to');
    first = from;
    last = to;
  } else {
    return bad('give --month, or --from and --to');
  }
  if (files.length === 0) return bad('no timesheet given');

  // The script checks the rate card, the client, and the timesheets, in that order.
  const checked = script(['--rates', rates, '--client', client, '--json', ...files]);
  if (checked.status !== 0) return failure(checked.stderr.replace(/^invoice\.py: /gm, 'hours invoice: '));

  const billable: string[] = [];
  let skipped = 0;
  let skippedMinutes = 0;
  for (const e of readTimesheets(files)) {
    if (e.client !== client || e.date < first || e.date > last) continue;
    if (e.note.split(' ').includes('+nobill')) {
      skipped += 1;
      skippedMinutes += e.minutes;
    } else {
      billable.push(`${e.date}  ${e.minutes}m  ${e.project}`);
    }
  }
  const dir = mkdtempSync(join(tmpdir(), 'hours-invoice-'));
  let bill: Billed;
  try {
    const sheet = join(dir, 'billable.txt');
    writeFileSync(sheet, billable.join('\n') + '\n');
    const r = script(['--rates', rates, '--client', client, '--json', sheet]);
    if (r.status !== 0) return failure(r.stderr);
    bill = JSON.parse(r.stdout) as Billed;
  } finally {
    rmSync(dir, { recursive: true, force: true });
  }

  const out = [`Invoice for ${bill.name} (${client})`, `Period: ${first} to ${last}`, `Currency: ${bill.currency}`, ''];
  if (bill.projects.length === 0) {
    out.push('Nothing to bill.');
  } else {
    const rows = [['Project', 'Entries', 'Time', 'Billed', 'Rate', 'Amount']];
    for (const p of bill.projects) {
      rows.push([p.project, String(p.entries), formatMinutes(p.minutes), formatMinutes(p.billed_minutes), p.rate, p.amount]);
    }
    out.push(...renderTable(rows, ['left', 'right', 'right', 'right', 'right', 'right']), '');
    const totals = [['Subtotal', bill.subtotal]];
    if (bill.tax_percent !== '0') totals.push([`Tax ${bill.tax_percent}%`, bill.tax]);
    totals.push(['Total', bill.total]);
    out.push(...renderTable(totals, ['left', 'right']));
  }
  if (skipped > 0) out.push('', `Not billed: ${formatMinutes(skippedMinutes)} in ${skipped} ${skipped === 1 ? 'entry' : 'entries'}`);
  return ok(out.map((l) => `${l}\n`).join(''));
}
