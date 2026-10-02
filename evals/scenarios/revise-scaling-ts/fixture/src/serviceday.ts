// Tap times are the reader's local wall-clock time, YYYY-MM-DDTHH:MM:SS. They are compared as plain clock
// readings (no time zone), so they are turned into seconds as if they were UTC.
//
// A service day runs from 04:00 to 03:59 the next morning: a tap at 00:40 belongs to the day before.

const TIMESTAMP = /^(\d{4})-(\d{2})-(\d{2})T(\d{2}):(\d{2}):(\d{2})$/;
const SERVICE_DAY_STARTS = 4 * 3600;

export function parseTimestamp(ts: string): number | null {
  const m = TIMESTAMP.exec(ts);
  if (!m) return null;
  const [y, mo, d, h, mi, s] = m.slice(1).map(Number);
  if (mo < 1 || mo > 12 || d < 1 || d > 31 || h > 23 || mi > 59 || s > 59) return null;
  const ms = Date.UTC(y, mo - 1, d, h, mi, s);
  if (new Date(ms).getUTCDate() !== d) return null; // 2026-02-30 and the like
  return ms / 1000;
}

export function serviceDay(seconds: number): string {
  return new Date((seconds - SERVICE_DAY_STARTS) * 1000).toISOString().slice(0, 10);
}

export function clock(ts: string): string {
  return ts.slice(11, 16);
}
