// hours invoice: one client's time for one period, billed by the rate card (docs/invoice.md).

import { parseArgs } from 'node:util';
import { daysInMonth, isDate } from '../dates.ts';
import { formatMinutes } from '../duration.ts';
import { amountCents, formatCents, formatPercent, taxCents } from '../money.ts';
import { type Client, RateCardError, readRateCard } from '../rates.ts';
import { failure, ok, type Result, usageError } from '../result.ts';
import { renderTable } from '../table.ts';
import { readAll } from '../parallel.ts';
import { type Entry, ReadError } from '../timesheet.ts';

export const INVOICE_USAGE =
  'usage: hours invoice --client CLIENT --rates FILE (--month YYYY-MM | --from DATE --to DATE) TIMESHEET...';

const MONTH = /^(\d{4})-(\d{2})$/;
const NOT_BILLED = '+nobill';

export interface ProjectLine {
  project: string;
  entries: number;
  minutes: number;
  billed: number;
  rate: number;
  amount: number;
}

export interface Bill {
  projects: ProjectLine[];
  subtotal: number;
  tax: number;
  total: number;
  notBilled: { entries: number; minutes: number };
}

/** The entry's time after the client's rounding: up to the increment, then at least the minimum. */
export function billedMinutes(minutes: number, client: Client): number {
  const rounded = Math.ceil(minutes / client.increment) * client.increment;
  return Math.max(rounded, client.minimum);
}

/** Bill the client's entries dated first..last (inclusive). */
export function bill(client: Client, entries: Entry[], first: string, last: string): Bill {
  const lines = new Map<string, ProjectLine>();
  const notBilled = { entries: 0, minutes: 0 };
  for (const e of entries) {
    if (e.client !== client.id || e.date < first || e.date > last) continue;
    if (e.note.split(' ').includes(NOT_BILLED)) {
      notBilled.entries += 1;
      notBilled.minutes += e.minutes;
      continue;
    }
    let line = lines.get(e.project);
    if (!line) {
      const name = e.project.slice(e.client.length + 1);
      line = { project: e.project, entries: 0, minutes: 0, billed: 0, rate: client.projectRates.get(name) ?? client.rate, amount: 0 };
      lines.set(e.project, line);
    }
    line.entries += 1;
    line.minutes += e.minutes;
    line.billed += billedMinutes(e.minutes, client);
  }
  const projects = [...lines.values()].sort((a, b) => (a.project < b.project ? -1 : a.project > b.project ? 1 : 0));
  let subtotal = 0;
  for (const p of projects) {
    p.amount = amountCents(p.billed, p.rate);
    subtotal += p.amount;
  }
  const tax = taxCents(subtotal, client.tax);
  return { projects, subtotal, tax, total: subtotal + tax, notBilled };
}

export function renderInvoice(client: Client, first: string, last: string, b: Bill): string {
  const out = [`Invoice for ${client.name} (${client.id})`, `Period: ${first} to ${last}`, `Currency: ${client.currency}`, ''];
  if (b.projects.length === 0) {
    out.push('Nothing to bill.');
  } else {
    const rows = [['Project', 'Entries', 'Time', 'Billed', 'Rate', 'Amount']];
    for (const p of b.projects) {
      rows.push([p.project, String(p.entries), formatMinutes(p.minutes), formatMinutes(p.billed), formatCents(p.rate), formatCents(p.amount)]);
    }
    out.push(...renderTable(rows, ['left', 'right', 'right', 'right', 'right', 'right']), '');
    const totals = [['Subtotal', formatCents(b.subtotal)]];
    if (client.tax !== 0) totals.push([`Tax ${formatPercent(client.tax)}%`, formatCents(b.tax)]);
    totals.push(['Total', formatCents(b.total)]);
    out.push(...renderTable(totals, ['left', 'right']));
  }
  if (b.notBilled.entries > 0) {
    const n = b.notBilled.entries;
    out.push('', `Not billed: ${formatMinutes(b.notBilled.minutes)} in ${n} ${n === 1 ? 'entry' : 'entries'}`);
  }
  return out.map((l) => `${l}\n`).join('');
}

export async function invoice(args: string[]): Promise<Result> {
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

  const { client: id, rates, month, from, to } = values;
  if (id === undefined) return bad('--client is required');
  if (rates === undefined) return bad('--rates is required');
  let first: string;
  let last: string;
  if (month !== undefined) {
    if (from !== undefined || to !== undefined) return bad('give either --month or --from and --to');
    const m = MONTH.exec(month);
    const year = m ? Number(m[1]) : 0;
    const mon = m ? Number(m[2]) : 0;
    if (!m || mon < 1 || mon > 12) return bad(`bad month "${month}"`);
    first = `${m[1]}-${m[2]}-01`;
    last = `${m[1]}-${m[2]}-${String(daysInMonth(year, mon)).padStart(2, '0')}`;
  } else if (from !== undefined || to !== undefined) {
    if (from === undefined || to === undefined) return bad('--from and --to go together');
    for (const date of [from, to]) if (!isDate(date)) return bad(`bad date "${date}"`);
    if (from > to) return bad('--from is after --to');
    first = from;
    last = to;
  } else {
    return bad('give --month, or --from and --to');
  }
  if (files.length === 0) return bad('no timesheet given');

  let client: Client | undefined;
  try {
    client = readRateCard(rates).get(id);
  } catch (error) {
    if (error instanceof RateCardError) return failure(error.message);
    if (error instanceof ReadError) return failure(`hours invoice: ${error.message}`);
    throw error;
  }
  if (!client) return failure(`hours invoice: no client "${id}" in ${rates}`);

  const entries: Entry[] = [];
  for (const r of await readAll(files)) {
    if ('error' in r) {
      if (r.error.kind === 'sheet') return failure(r.error.message);
      if (r.error.kind === 'read') return failure(`hours invoice: ${r.error.message}`);
      throw new Error(r.error.message);
    }
    entries.push(...r.entries);
  }
  return ok(renderInvoice(client, first, last, bill(client, entries, first, last)));
}
