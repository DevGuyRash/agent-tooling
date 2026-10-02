// hours invoice --client CLIENT --rates FILE (--month YYYY-MM | --from DATE --to DATE) TIMESHEET...
// Everything the command needs beyond reading timesheets lives here: the rate card, the arithmetic (bigint
// cents), and the layout.

import { readFileSync } from 'node:fs';
import { isDate } from '../dates.ts';
import { formatMinutes } from '../duration.ts';
import type { Result } from '../result.ts';
import { ReadError, TimesheetError, readTimesheets } from '../timesheet.ts';

const USAGE = 'usage: hours invoice --client CLIENT --rates FILE (--month YYYY-MM | --from DATE --to DATE) TIMESHEET...';

class Stop {
  result: Result;
  constructor(code: number, message: string) {
    this.result = { code, stdout: '', stderr: `${message}\n` };
  }
}

const usage = (message: string) => new Stop(2, `hours invoice: ${message}\n${USAGE}`);

type Rate = { name?: string; currency?: string; rate?: bigint; increment: bigint; minimum: bigint; tax: bigint; projects: Record<string, bigint> };

function decimal(text: string, scale = 100n): bigint | undefined {
  const m = /^(\d+)(?:\.(\d\d?))?$/.exec(text);
  if (!m) return undefined;
  return BigInt(m[1]) * scale + BigInt((m[2] ?? '0').padEnd(2, '0'));
}

function rateCard(file: string): Map<string, Rate> {
  let text: string;
  try {
    text = readFileSync(file, 'utf8');
  } catch (error) {
    throw new Stop(1, `hours invoice: ${new ReadError(file, error).message}`);
  }
  const card = new Map<string, Rate>();
  let id = '';
  let headerLine = 0;
  let seen = new Set<string>();
  const fail = (line: number, what: string) => new Stop(1, `${file}:${line}: ${what}`);
  const finish = () => {
    for (const key of ['name', 'currency', 'rate']) if (id && !seen.has(key)) throw fail(headerLine, `[${id}] has no ${key}`);
  };
  text.split('\n').forEach((raw, index) => {
    const n = index + 1;
    const line = raw.trim();
    if (!line || line[0] === '#') return;
    const header = line.match(/^\[([a-z0-9-]+)\]$/);
    if (header) {
      finish();
      [id, headerLine, seen] = [header[1], n, new Set()];
      if (card.has(id)) throw fail(n, `client ${id} is given twice`);
      card.set(id, { increment: 1n, minimum: 0n, tax: 0n, projects: {} });
      return;
    }
    const kv = line.match(/^([^=]*)=(.*)$/);
    if (!kv) throw fail(n, 'not a [CLIENT] or key = value line');
    const [key, value] = [kv[1].trim(), kv[2].trim()];
    if (!id) throw fail(n, 'setting before any [CLIENT]');
    const entry = card.get(id) as Rate;
    const project = /^rate\.([a-z0-9-]+)$/.exec(key)?.[1];
    if (seen.has(key)) throw fail(n, `${key} given twice`);
    let ok: boolean;
    switch (project === undefined ? key : 'rate.*') {
      case 'name':
        ok = value !== '';
        entry.name = value;
        break;
      case 'currency':
        ok = /^[A-Z]{3}$/.test(value);
        entry.currency = value;
        break;
      case 'rate':
      case 'rate.*': {
        const cents = decimal(value);
        ok = cents !== undefined;
        if (project === undefined) entry.rate = cents;
        else if (cents !== undefined) entry.projects[project] = cents;
        break;
      }
      case 'increment':
      case 'minimum':
        ok = /^\d+$/.test(value) && (key === 'minimum' || BigInt(value) > 0n);
        if (ok) entry[key] = BigInt(value);
        break;
      case 'tax': {
        const hundredths = decimal(value);
        ok = hundredths !== undefined && hundredths <= 10000n;
        if (ok) entry.tax = hundredths as bigint;
        break;
      }
      default:
        throw fail(n, `no such setting: ${key}`);
    }
    if (!ok) throw fail(n, `${key} = ${value} is not valid`);
    seen.add(key);
  });
  finish();
  return card;
}

function lastDayOfMonth(year: number, month: number): number {
  return new Date(Date.UTC(year, month, 0)).getUTCDate();
}

function options(args: string[]): { client: string; rates: string; first: string; last: string; files: string[] } {
  const known = ['--client', '--rates', '--month', '--from', '--to'];
  const opts = new Map<string, string>();
  const files: string[] = [];
  for (let i = 0; i < args.length; i++) {
    const arg = args[i];
    if (arg === '--') {
      files.push(...args.slice(i + 1));
      break;
    }
    if (!arg.startsWith('-') || arg === '-') {
      files.push(arg);
      continue;
    }
    const [flag, inline] = arg.includes('=') ? [arg.slice(0, arg.indexOf('=')), arg.slice(arg.indexOf('=') + 1)] : [arg, undefined];
    if (!known.includes(flag)) throw usage(`unknown option ${flag}`);
    const value = inline ?? args[++i];
    if (value === undefined || (inline === undefined && value.startsWith('--'))) throw usage(`${flag} needs a value`);
    opts.set(flag.slice(2), value);
  }
  const client = opts.get('client');
  const rates = opts.get('rates');
  if (!client) throw usage('--client is required');
  if (!rates) throw usage('--rates is required');
  const month = opts.get('month');
  const from = opts.get('from');
  const to = opts.get('to');
  let first: string;
  let last: string;
  if (month !== undefined && (from !== undefined || to !== undefined)) throw usage('--month cannot go with --from or --to');
  if (month !== undefined) {
    const m = /^(\d{4})-(0[1-9]|1[0-2])$/.exec(month);
    if (!m) throw usage(`${month} is not a month (YYYY-MM)`);
    first = `${month}-01`;
    last = `${month}-${String(lastDayOfMonth(Number(m[1]), Number(m[2]))).padStart(2, '0')}`;
  } else {
    if (from === undefined && to === undefined) throw usage('a period is required: --month, or --from and --to');
    if (from === undefined || to === undefined) throw usage('--from and --to must both be given');
    if (!isDate(from) || !isDate(to)) throw usage('dates are YYYY-MM-DD');
    if (from > to) throw usage(`${from} is after ${to}`);
    [first, last] = [from, to];
  }
  if (files.length === 0) throw usage('which timesheets?');
  return { client, rates, first, last, files };
}

const money = (cents: bigint) => `${cents / 100n}.${String(cents % 100n).padStart(2, '0')}`;
const roundedDiv = (n: bigint, d: bigint) => (n * 2n + d) / (d * 2n);
const percent = (h: bigint) => (h % 100n === 0n ? `${h / 100n}` : `${h / 100n}.${String(h % 100n).padStart(2, '0')}`.replace(/0$/, ''));

function columns(rows: string[][], rightFrom: number): string[] {
  const width = rows[0].map((_, c) => Math.max(...rows.map((r) => r[c].length)));
  return rows.map((r) => r.map((cell, c) => (c >= rightFrom ? cell.padStart(width[c]) : cell.padEnd(width[c]))).join('  ').replace(/ +$/, ''));
}

export function invoice(args: string[]): Result {
  try {
    const { client, rates, first, last, files } = options(args);
    const card = rateCard(rates);
    const rate = card.get(client);
    if (!rate) throw new Stop(1, `hours invoice: no client "${client}" in ${rates}`);
    let entries;
    try {
      entries = readTimesheets(files);
    } catch (error) {
      if (error instanceof TimesheetError) throw new Stop(1, error.message);
      if (error instanceof ReadError) throw new Stop(1, `hours invoice: ${error.message}`);
      throw error;
    }

    const perProject: Record<string, { n: number; minutes: number; billed: bigint }> = {};
    let skipped = 0;
    let skippedMinutes = 0;
    for (const e of entries) {
      if (e.client !== client || e.date < first || e.date > last) continue;
      if (/(^|\s)\+nobill(\s|$)/.test(e.note)) {
        skipped++;
        skippedMinutes += e.minutes;
        continue;
      }
      const p = (perProject[e.project] ??= { n: 0, minutes: 0, billed: 0n });
      const m = BigInt(e.minutes);
      const up = ((m + rate.increment - 1n) / rate.increment) * rate.increment;
      p.n++;
      p.minutes += e.minutes;
      p.billed += up > rate.minimum ? up : rate.minimum;
    }

    const lines = [`Invoice for ${rate.name} (${client})`, `Period: ${first} to ${last}`, `Currency: ${rate.currency}`, ''];
    const names = Object.keys(perProject).sort();
    if (names.length) {
      let subtotal = 0n;
      const rows = [['Project', 'Entries', 'Time', 'Billed', 'Rate', 'Amount']];
      for (const name of names) {
        const p = perProject[name];
        const hourly = rate.projects[name.split('/')[1]] ?? (rate.rate as bigint);
        const amount = roundedDiv(p.billed * hourly, 60n);
        subtotal += amount;
        rows.push([name, `${p.n}`, formatMinutes(p.minutes), formatMinutes(Number(p.billed)), money(hourly), money(amount)]);
      }
      const tax = roundedDiv(subtotal * rate.tax, 10000n);
      const totals = [['Subtotal', money(subtotal)], ...(rate.tax ? [[`Tax ${percent(rate.tax)}%`, money(tax)]] : []), ['Total', money(subtotal + tax)]];
      lines.push(...columns(rows, 1), '', ...columns(totals, 1));
    } else {
      lines.push('Nothing to bill.');
    }
    if (skipped) lines.push('', `Not billed: ${formatMinutes(skippedMinutes)} in ${skipped} ${skipped > 1 ? 'entries' : 'entry'}`);
    return { code: 0, stdout: lines.join('\n') + '\n', stderr: '' };
  } catch (error) {
    if (error instanceof Stop) return error.result;
    throw error;
  }
}
