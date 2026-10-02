// hours check FILE...: every line parses, and no two ranges on the same day overlap within a file.

import { parseArgs } from 'node:util';
import { formatMinutes } from '../duration.ts';
import { type Result, usageError } from '../result.ts';
import { type Entry, ReadError, TimesheetError, readTimesheet } from '../timesheet.ts';

export const CHECK_USAGE = 'usage: hours check FILE...';

/** Lines of entries that start before an earlier-starting range on the same day has ended. */
function overlaps(entries: Entry[]): string[] {
  const byDate = new Map<string, Entry[]>();
  for (const e of entries) {
    if (e.start === null) continue;
    const list = byDate.get(e.date);
    if (list) list.push(e);
    else byDate.set(e.date, [e]);
  }
  const found: Entry[] = [];
  const against = new Map<Entry, Entry>();
  for (const list of byDate.values()) {
    list.sort((a, b) => (a.start as number) - (b.start as number) || a.line - b.line);
    let latest: Entry | undefined;
    for (const e of list) {
      if (latest && (e.start as number) < (latest.end as number)) {
        found.push(e);
        against.set(e, latest);
      }
      if (!latest || (e.end as number) > (latest.end as number)) latest = e;
    }
  }
  found.sort((a, b) => a.line - b.line);
  return found.map((e) => `${e.file}:${e.line}: overlaps line ${against.get(e)?.line}`);
}

export function check(args: string[]): Result {
  let files: string[];
  try {
    files = parseArgs({ args, options: {}, allowPositionals: true, strict: true }).positionals;
  } catch (error) {
    return usageError('check', (error as Error).message, CHECK_USAGE);
  }
  if (files.length === 0) return usageError('check', 'no timesheet given', CHECK_USAGE);

  const out: string[] = [];
  const err: string[] = [];
  for (const file of files) {
    let entries: Entry[];
    try {
      entries = readTimesheet(file);
    } catch (error) {
      if (error instanceof TimesheetError) err.push(error.message);
      else if (error instanceof ReadError) err.push(`hours check: ${error.message}`);
      else throw error;
      continue;
    }
    const problems = overlaps(entries);
    if (problems.length > 0) {
      err.push(...problems);
      continue;
    }
    const total = entries.reduce((sum, e) => sum + e.minutes, 0);
    out.push(`${file}: ${entries.length} ${entries.length === 1 ? 'entry' : 'entries'}, ${formatMinutes(total)}`);
  }
  return {
    code: err.length > 0 ? 1 : 0,
    stdout: out.map((l) => `${l}\n`).join(''),
    stderr: err.map((l) => `${l}\n`).join(''),
  };
}
