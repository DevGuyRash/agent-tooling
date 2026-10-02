// Dates are ISO calendar dates ("2026-09-01"), compared as strings.

const ISO_DATE = /^(\d{4})-(\d{2})-(\d{2})$/;

export function isLeapYear(year: number): boolean {
  return (year % 4 === 0 && year % 100 !== 0) || year % 400 === 0;
}

export function daysInMonth(year: number, month: number): number {
  if (month === 2) return isLeapYear(year) ? 29 : 28;
  return [4, 6, 9, 11].includes(month) ? 30 : 31;
}

/** True for a real date written YYYY-MM-DD. */
export function isDate(text: string): boolean {
  const m = ISO_DATE.exec(text);
  if (!m) return false;
  const year = Number(m[1]);
  const month = Number(m[2]);
  const day = Number(m[3]);
  return month >= 1 && month <= 12 && day >= 1 && day <= daysInMonth(year, month);
}

/** True when date is within [from, to]; a missing bound is open. */
export function inRange(date: string, from?: string, to?: string): boolean {
  return (from === undefined || date >= from) && (to === undefined || date <= to);
}
