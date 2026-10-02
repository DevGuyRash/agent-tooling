// Reading timesheets: one entry per line, DATE TIME PROJECT [NOTE]. The format is in docs/timesheets.md.

import { readFileSync } from 'node:fs';
import { isDate } from './dates.ts';
import { parseClock, parseDuration } from './duration.ts';

export interface Entry {
  file: string;
  line: number;
  date: string;
  /** Minutes after midnight, for entries written as a range; null for durations. */
  start: number | null;
  end: number | null;
  minutes: number;
  /** The part of the project before the slash: "acme" for "acme/site". */
  client: string;
  /** The whole project, "acme/site". */
  project: string;
  note: string;
  /** The words of the note (separated by spaces or tabs in the file). */
  words: string[];
}

/** A line of a timesheet that is not an entry, a comment, or blank. */
export class TimesheetError extends Error {
  file: string;
  line: number;

  constructor(file: string, line: number, detail: string) {
    super(`${file}:${line}: ${detail}`);
    this.name = 'TimesheetError';
    this.file = file;
    this.line = line;
  }
}

/** A timesheet that cannot be read at all. */
export class ReadError extends Error {
  file: string;

  constructor(file: string, cause: unknown) {
    super(`cannot read ${file}: ${cause instanceof Error && 'code' in cause ? String(cause.code) : String(cause)}`);
    this.name = 'ReadError';
    this.file = file;
  }
}

const PROJECT = /^([a-z0-9-]+)\/[a-z0-9-]+$/;
const RANGE = /^(\d\d:\d\d)-(\d\d:\d\d)$/;

export function parseTimesheet(text: string, file: string): Entry[] {
  const entries: Entry[] = [];
  const lines = text.split('\n');
  for (let i = 0; i < lines.length; i++) {
    const line = i + 1;
    const trimmed = lines[i].trim();
    if (trimmed === '' || trimmed.startsWith('#')) continue;
    const fields = trimmed.split(/[ \t]+/);
    if (fields.length < 3) throw new TimesheetError(file, line, 'expected DATE TIME PROJECT [NOTE]');
    const [date, time, project] = fields;
    if (!isDate(date)) throw new TimesheetError(file, line, `bad date "${date}"`);
    let start: number | null = null;
    let end: number | null = null;
    let minutes: number;
    const range = RANGE.exec(time);
    if (range) {
      start = parseClock(range[1]);
      end = parseClock(range[2]);
      if (start === null || end === null) throw new TimesheetError(file, line, `bad time "${time}"`);
      if (end <= start) throw new TimesheetError(file, line, `"${time}" ends before it starts`);
      minutes = end - start;
    } else {
      const duration = parseDuration(time);
      if (duration === null) throw new TimesheetError(file, line, `bad time "${time}"`);
      minutes = duration;
    }
    const p = PROJECT.exec(project);
    if (!p) throw new TimesheetError(file, line, `bad project "${project}"`);
    entries.push({ file, line, date, start, end, minutes, client: p[1], project, note: fields.slice(3).join(' '), words: fields.slice(3) });
  }
  return entries;
}

export function readTimesheet(file: string): Entry[] {
  let text: string;
  try {
    text = readFileSync(file, 'utf8');
  } catch (error) {
    throw new ReadError(file, error);
  }
  return parseTimesheet(text, file);
}

/** Every entry of every file, in the order given; the first unreadable file or bad line throws. */
export function readTimesheets(files: string[]): Entry[] {
  return files.flatMap((file) => readTimesheet(file));
}
