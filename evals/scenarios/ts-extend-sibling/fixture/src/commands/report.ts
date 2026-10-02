// hours report: time per project, client, or date, optionally for a range of dates.

import { parseArgs } from 'node:util';
import { inRange, isDate } from '../dates.ts';
import { formatMinutes } from '../duration.ts';
import { failure, ok, type Result, usageError } from '../result.ts';
import { renderTable } from '../table.ts';
import { type Entry, ReadError, TimesheetError, readTimesheets } from '../timesheet.ts';

export const REPORT_USAGE = 'usage: hours report [--from DATE] [--to DATE] [--by project|client|date] FILE...';

const KEYS: Record<string, { header: string; key: (e: Entry) => string }> = {
  project: { header: 'Project', key: (e) => e.project },
  client: { header: 'Client', key: (e) => e.client },
  date: { header: 'Date', key: (e) => e.date },
};

export function report(args: string[]): Result {
  let values: { from?: string; to?: string; by?: string };
  let files: string[];
  try {
    const parsed = parseArgs({
      args,
      options: { from: { type: 'string' }, to: { type: 'string' }, by: { type: 'string' } },
      allowPositionals: true,
      strict: true,
    });
    values = parsed.values;
    files = parsed.positionals;
  } catch (error) {
    return usageError('report', (error as Error).message, REPORT_USAGE);
  }
  const { from, to } = values;
  const by = values.by ?? 'project';
  for (const date of [from, to]) {
    if (date !== undefined && !isDate(date)) return usageError('report', `bad date "${date}"`, REPORT_USAGE);
  }
  if (!Object.hasOwn(KEYS, by)) return usageError('report', `cannot report by "${by}"`, REPORT_USAGE);
  if (files.length === 0) return usageError('report', 'no timesheet given', REPORT_USAGE);

  let entries: Entry[];
  try {
    entries = readTimesheets(files);
  } catch (error) {
    if (error instanceof TimesheetError) return failure(error.message);
    if (error instanceof ReadError) return failure(`hours report: ${error.message}`);
    throw error;
  }

  const { header, key } = KEYS[by];
  const groups = new Map<string, { entries: number; minutes: number }>();
  let count = 0;
  let minutes = 0;
  for (const e of entries) {
    if (!inRange(e.date, from, to)) continue;
    const k = key(e);
    const g = groups.get(k) ?? { entries: 0, minutes: 0 };
    g.entries += 1;
    g.minutes += e.minutes;
    groups.set(k, g);
    count += 1;
    minutes += e.minutes;
  }
  const rows = [[header, 'Entries', 'Time']];
  for (const k of [...groups.keys()].sort()) {
    const g = groups.get(k) as { entries: number; minutes: number };
    rows.push([k, String(g.entries), formatMinutes(g.minutes)]);
  }
  rows.push(['Total', String(count), formatMinutes(minutes)]);
  return ok(renderTable(rows, ['left', 'right', 'right']).map((l) => `${l}\n`).join(''));
}
