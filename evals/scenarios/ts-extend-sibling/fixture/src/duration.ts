// Times are whole minutes. Timesheets write a duration as "2h", "1h15", or "45m"; reports print "h:mm".

const DURATION = /^(?:(\d+)h([0-5]\d)?|(\d+)m)$/;
const CLOCK = /^([01]\d|2[0-3]):([0-5]\d)$/;

/** Minutes in a duration such as "1h15", or null when it is not one (or is zero). */
export function parseDuration(text: string): number | null {
  const m = DURATION.exec(text);
  if (!m) return null;
  const minutes = m[3] !== undefined ? Number(m[3]) : Number(m[1]) * 60 + Number(m[2] ?? '0');
  return minutes > 0 ? minutes : null;
}

/** Minutes after midnight for "HH:MM" on a 24-hour clock, or null. */
export function parseClock(text: string): number | null {
  const m = CLOCK.exec(text);
  return m ? Number(m[1]) * 60 + Number(m[2]) : null;
}

/** "h:mm", such as "0:05" or "126:30". */
export function formatMinutes(minutes: number): string {
  const h = Math.floor(minutes / 60);
  const m = minutes % 60;
  return `${h}:${String(m).padStart(2, '0')}`;
}
